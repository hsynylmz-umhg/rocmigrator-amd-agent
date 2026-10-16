"""HTTP and SSE regressions for the engine-backed migration API."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient

from agent_orchestrator import engine
from backend.app.api import routes
from backend.app.services.stream import SSELogStreamer
from contracts.api_schemas import JobCreateRequest, JobStatusResponse, LogEvent
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import VerificationReport
from tests._openai_stub import install_offline_patch_client


EXPECTED_PIPELINE_STATES = [
    PipelineState.CREATED,
    PipelineState.CLONING,
    PipelineState.SECURITY_SCAN,
    PipelineState.ANALYSIS,
    PipelineState.BASELINE,
    PipelineState.HIPIFICATION,
    PipelineState.COMPILING,
    PipelineState.REPAIR,
    PipelineState.COMPILING,
    PipelineState.VERIFYING,
    PipelineState.ROLLED_BACK,
]


class TestMigrationAPI(unittest.TestCase):
    def setUp(self):
        self.create_completion = install_offline_patch_client(self)
        task_store = patch.dict(engine._job_statuses, clear=True)
        task_store.start()
        self.addCleanup(task_store.stop)
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def assert_lifecycle_headers(self, response):
        self.assertNotIn("X-ROCmigrator-Mode", response.headers)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def start_task(self, path="/api/migrate", **changes):
        payload = {"repo_path": "fixtures/golden-repo-01"}
        payload.update(changes)
        response = self.client.post(path, json=payload)
        self.assertEqual(response.status_code, 202, response.text)
        self.assert_lifecycle_headers(response)
        status = JobStatusResponse.model_validate_json(response.content)
        self.assertEqual(status.current_state, PipelineState.CREATED)
        self.assertIsNone(status.verification_report)
        self.assertEqual(urlsplit(response.headers["Location"]).path, f"/api/status/{status.job_id}")
        self.assertTrue(status.job_id.startswith("job-"))
        UUID(status.job_id.removeprefix("job-"))
        return status.job_id

    def test_start_runs_engine_repair_and_exposes_its_failed_verification(self):
        task_id = self.start_task()
        self.create_completion.assert_awaited_once()

        status_response = self.client.get(f"/api/status/{task_id}")
        self.assertEqual(status_response.status_code, 200)
        self.assert_lifecycle_headers(status_response)
        status = JobStatusResponse.model_validate_json(status_response.content)
        self.assertEqual(status.job_id, task_id)
        self.assertEqual(status.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(status.repair_rounds_used, 1)
        self.assertIsNone(status.best_known_commit)
        self.assertEqual(status, engine.get_migration_status(task_id))

        report_response = self.client.get(f"/api/report/{task_id}")
        self.assertEqual(report_response.status_code, 200)
        self.assert_lifecycle_headers(report_response)
        report = VerificationReport.model_validate_json(report_response.content)
        self.assertEqual(report, status.verification_report)
        self.assertEqual(report.job_id, task_id)
        self.assertEqual(report.overall_status, "FAILED")
        self.assertFalse(report.cpu_reference_verified)
        self.assertFalse(report.determinism_passed)
        self.assertEqual(report.results, ())
        self.assertEqual((report.total_tests, report.passed_tests, report.failed_tests), (0, 0, 0))
        self.assertIn("SIMULATION", report.summary)

    def test_background_pipeline_receives_validated_request_without_route_storage(self):
        payload = {
            "repo_path": "fixtures/golden-repo-02",
            "target_branch": "custom-hip-port",
            "max_repair_rounds": 2,
        }
        with patch.object(routes, "run_migration_pipeline", new_callable=AsyncMock) as run:
            task_id = self.start_task(**payload)
        run.assert_awaited_once_with(task_id, JobCreateRequest(**payload))
        self.assertIsInstance(run.await_args.args[1], JobCreateRequest)
        self.assertEqual(engine._job_statuses, {})

    def test_status_reads_engine_snapshot_and_pending_report_returns_retry_header(self):
        task_id = "job-engine-owned"
        snapshot = JobStatusResponse(
            job_id=task_id,
            current_state=PipelineState.REPAIR,
            repair_rounds_used=2,
            best_known_commit="0123456789abcdef",
        )
        engine._job_statuses[task_id] = snapshot

        status_response = self.client.get(f"/api/status/{task_id}")
        self.assertEqual(status_response.status_code, 200)
        status = JobStatusResponse.model_validate_json(status_response.content)
        self.assertEqual(status, snapshot)
        self.assertIsNone(status.verification_report)

        pending = self.client.get(f"/api/report/{task_id}")
        self.assertEqual(pending.status_code, 409)
        self.assert_lifecycle_headers(pending)
        self.assertEqual(pending.headers["Retry-After"], "1")
        self.assertIn("detail", pending.json())

    def test_unique_identifiers_and_legacy_job_aliases(self):
        canonical_id = self.start_task()
        legacy_id = self.start_task(path="/api/jobs")
        self.assertNotEqual(canonical_id, legacy_id)
        self.assertEqual(len(engine._job_statuses), 2)

        for task_id in (canonical_id, legacy_id):
            with self.subTest(task_id=task_id):
                canonical = self.client.get(f"/api/status/{task_id}")
                legacy = self.client.get(f"/api/jobs/{task_id}")
                self.assertEqual(legacy.status_code, 200)
                self.assert_lifecycle_headers(legacy)
                self.assertEqual(legacy.json(), canonical.json())
                report = VerificationReport.model_validate_json(
                    self.client.get(f"/api/report/{task_id}").content
                )
                self.assertEqual(report.job_id, task_id)

    def test_strict_request_validation_rejects_coercion_and_unknown_fields(self):
        invalid_payloads = [
            {},
            {"repo_path": "   "},
            {"repo_path": 42},
            {"repo_path": "repo", "target_branch": False},
            {"repo_path": "repo", "max_repair_rounds": True},
            {"repo_path": "repo", "max_repair_rounds": "6"},
            {"repo_path": "repo", "max_repair_rounds": 0},
            {"repo_path": "repo", "max_repair_rounds": 7},
            {"repo_path": "repo", "command": "unexpected"},
        ]
        with patch.object(routes, "run_migration_pipeline", new_callable=AsyncMock) as run:
            for endpoint in ("/api/migrate", "/api/jobs"):
                for payload in invalid_payloads:
                    with self.subTest(endpoint=endpoint, payload=payload):
                        response = self.client.post(endpoint, json=payload)
                        self.assertEqual(response.status_code, 422, response.text)
            run.assert_not_called()
        self.assertEqual(engine._job_statuses, {})

    def test_missing_task_returns_404(self):
        for endpoint in ("/api/status/missing", "/api/report/missing", "/api/jobs/missing"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 404)
                self.assert_lifecycle_headers(response)
                self.assertIn("detail", response.json())

        approval = self.client.post(
            "/api/jobs/missing/approve", json={"job_id": "missing", "approved": True}
        )
        self.assertEqual(approval.status_code, 404)
        self.assert_lifecycle_headers(approval)

    def test_unconnected_approval_fails_closed_and_keeps_report_unchanged(self):
        task_id = self.start_task()
        original = self.client.get(f"/api/status/{task_id}").json()
        for decision in (True, False):
            with self.subTest(decision=decision):
                approval = self.client.post(
                    f"/api/jobs/{task_id}/approve",
                    json={"job_id": task_id, "approved": decision},
                )
                self.assertEqual(approval.status_code, 503)
                self.assert_lifecycle_headers(approval)
                self.assertIn("approval", approval.json()["detail"].lower())
                self.assertIn("connected", approval.json()["detail"].lower())
        self.assertEqual(self.client.get(f"/api/status/{task_id}").json(), original)

    def test_approval_rejects_different_job_and_nonboolean_decision(self):
        task_id = self.start_task()
        mismatch = self.client.post(
            f"/api/jobs/{task_id}/approve",
            json={"job_id": "another-job", "approved": True},
        )
        self.assertEqual(mismatch.status_code, 409)
        self.assert_lifecycle_headers(mismatch)

        for changes in ({"approved": "true"}, {"approved": 1}, {"unrecognized": True}):
            with self.subTest(changes=changes):
                payload = {"job_id": task_id, "approved": True, **changes}
                response = self.client.post(f"/api/jobs/{task_id}/approve", json=payload)
                self.assertEqual(response.status_code, 422)

    def test_async_entry_point_does_not_invoke_legacy_synchronous_engine(self):
        with (
            patch.object(
                engine.OrchestratorEngine, "__init__", side_effect=AssertionError("Legacy engine")
            ) as initialize,
            patch.object(
                engine.OrchestratorEngine,
                "run_pipeline",
                side_effect=AssertionError("Legacy pipeline"),
            ) as run_pipeline,
        ):
            task_id = self.start_task(repo_path="untrusted-repo; never-execute")
            self.assertEqual(self.client.get(f"/api/report/{task_id}").status_code, 200)
            initialize.assert_not_called()
            run_pipeline.assert_not_called()

    def test_engine_owns_failure_outcome(self):
        async def rejected_hipify(job_id):
            return LogEvent(
                job_id=job_id,
                state=PipelineState.HIPIFICATION,
                level="ERROR",
                message="Runner rejected this translation.",
            )

        with patch.object(engine, "_run_hipify_step", side_effect=rejected_hipify):
            task_id = self.start_task()
        snapshot = JobStatusResponse.model_validate_json(
            self.client.get(f"/api/status/{task_id}").content
        )
        self.assertEqual(snapshot, engine.get_migration_status(task_id))
        self.assertEqual(snapshot.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(snapshot.repair_rounds_used, 0)
        self.assertEqual(snapshot.verification_report.overall_status, "ROLLED_BACK")

    def test_strict_response_model_rejects_invalid_engine_snapshot(self):
        engine._job_statuses["job-invalid"] = JobStatusResponse.model_construct(
            job_id="job-invalid", current_state=PipelineState.CREATED, repair_rounds_used="1"
        )
        with self.assertRaises(ResponseValidationError):
            self.client.get("/api/status/job-invalid")

    def test_lifecycle_broadcasts_typed_events_for_the_same_task(self):
        with patch.object(routes.log_streamer, "broadcast", new_callable=AsyncMock) as broadcast:
            task_id = self.start_task()
        events = [call.args[0] for call in broadcast.await_args_list]
        self.assertEqual(
            [event.state for event in events if event.level == "STEP"],
            EXPECTED_PIPELINE_STATES,
        )
        for event in events:
            with self.subTest(event=event):
                self.assertIsInstance(event, LogEvent)
                self.assertEqual(event.job_id, task_id)
                self.assertEqual(LogEvent.model_validate_json(event.model_dump_json()), event)

    def test_openapi_exposes_contract_response_schemas(self):
        document = self.client.get("/openapi.json").json()
        for path, method, status, model in (
            ("/api/migrate", "post", "202", "JobStatusResponse"),
            ("/api/jobs", "post", "202", "JobStatusResponse"),
            ("/api/status/{task_id}", "get", "200", "JobStatusResponse"),
            ("/api/jobs/{task_id}", "get", "200", "JobStatusResponse"),
            ("/api/report/{task_id}", "get", "200", "VerificationReport"),
        ):
            with self.subTest(path=path):
                schema = document["paths"][path][method]["responses"][status]["content"][
                    "application/json"
                ]["schema"]
                self.assertEqual(schema["$ref"], f"#/components/schemas/{model}")
        request = document["paths"]["/api/migrate"]["post"]["requestBody"]
        self.assertTrue(request["required"])
        self.assertEqual(
            request["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/JobCreateRequest",
        )


class TestAsyncMigrationAPI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.create_completion = install_offline_patch_client(self)

    async def test_start_defers_engine_execution_to_background_task(self):
        app = FastAPI()
        app.include_router(routes.router)
        request = Request({
            "type": "http", "method": "POST", "scheme": "http",
            "path": "/api/migrate", "root_path": "", "query_string": b"",
            "headers": [], "server": ("testserver", 80), "router": app.router,
        })
        background_tasks = BackgroundTasks()
        with patch.dict(engine._job_statuses, clear=True):
            acknowledgement = await routes.start_migration(
                JobCreateRequest(repo_path="fixtures/golden-repo-01"),
                background_tasks, request, Response(),
            )
            self.assertEqual(acknowledgement.current_state, PipelineState.CREATED)
            self.assertEqual(engine._job_statuses, {})
            await background_tasks()
            snapshot = engine.get_migration_status(acknowledgement.job_id)
            self.assertEqual(snapshot.current_state, PipelineState.ROLLED_BACK)
            self.assertEqual(snapshot.repair_rounds_used, 1)

    async def test_sse_route_keeps_stream_headers_and_validated_json_frames(self):
        streamer = SSELogStreamer()
        event = LogEvent(
            job_id="job-example",
            state=PipelineState.CREATED,
            message="Pipeline accepted.",
        )
        with patch.object(routes, "log_streamer", streamer):
            response = await routes.sse_logs()
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            self.assertEqual(response.headers["Cache-Control"], "no-cache, no-transform")
            self.assertEqual(response.headers["Connection"], "keep-alive")
            self.assertEqual(response.headers["X-Accel-Buffering"], "no")
            self.assertNotIn("X-ROCmigrator-Mode", response.headers)
            self.assertEqual(await anext(response.body_iterator), ": connected\n\n")
            frame_task = asyncio.create_task(anext(response.body_iterator))
            try:
                await asyncio.sleep(0)
                await streamer.broadcast(event)
                frame = await asyncio.wait_for(frame_task, timeout=1.0)
                self.assertTrue(frame.startswith("data: "))
                self.assertTrue(frame.endswith("\n\n"))
                self.assertEqual(LogEvent.model_validate_json(frame[6:].strip()), event)
            finally:
                if not frame_task.done():
                    frame_task.cancel()
                    await asyncio.gather(frame_task, return_exceptions=True)
                await response.body_iterator.aclose()
        self.assertEqual(streamer._queues, [])

    async def test_engine_transitions_reach_route_sse_stream(self):
        streamer = SSELogStreamer()
        job_id = "job-streamed-engine"
        with (
            patch.dict(engine._job_statuses, clear=True),
            patch.object(routes, "log_streamer", streamer),
            patch.object(engine, "log_streamer", streamer),
        ):
            response = await routes.sse_logs()
            self.assertEqual(await anext(response.body_iterator), ": connected\n\n")
            pipeline = asyncio.create_task(engine.run_migration_pipeline(
                job_id, JobCreateRequest(repo_path="fixtures/golden-repo-01")
            ))
            events = []
            try:
                async with asyncio.timeout(3.0):
                    while True:
                        frame = await anext(response.body_iterator)
                        event = LogEvent.model_validate_json(frame[6:].strip())
                        self.assertEqual(event.job_id, job_id)
                        events.append(event)
                        if event.state == PipelineState.ROLLED_BACK and event.level == "STEP":
                            break
                    final_status = await pipeline
                self.assertEqual(
                    [event.state for event in events if event.level == "STEP"],
                    EXPECTED_PIPELINE_STATES,
                )
                self.assertEqual(final_status.current_state, PipelineState.ROLLED_BACK)
                self.assertEqual(final_status.repair_rounds_used, 1)
            finally:
                if not pipeline.done():
                    pipeline.cancel()
                    await asyncio.gather(pipeline, return_exceptions=True)
                await response.body_iterator.aclose()
        self.assertEqual(streamer._queues, [])


if __name__ == "__main__":
    unittest.main()
