"""Approval safety and GitHub reconciliation; all network writes use a fake client."""

import asyncio
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_orchestrator import engine
from backend.app.services import approval
from backend.app.api import routes
from contracts.api_schemas import ApprovalRequest, JobCreateRequest, JobStatusResponse
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import NumericalResult, VerificationReport


SOURCE = "a" * 40
TREE = "b" * 40
CHANGED_TREE = "c" * 40
COMMIT = "d" * 40
BLOB = "e" * 40
JOB = "job-approval-test"
BRANCH = f"codex/hip-port-{JOB}"
REPOSITORY = "owner/project"


def report(job_id=JOB):
    cases = [
        NumericalResult(seed=seed, shape=shape, dtype=dtype, atol=1e-5, rtol=1e-5,
                        max_abs_err=0.0, max_rel_err=0.0, mismatch_ratio=0.0,
                        nan_inf_detected=False, passed=True)
        for seed in (42, 1337) for shape in ((16,), (4, 4)) for dtype in ("float32", "float64")
    ]
    return VerificationReport(job_id=job_id, overall_status="VERIFIED", cpu_reference_verified=True,
                              determinism_passed=True, results=cases, total_tests=8,
                              passed_tests=8, failed_tests=0, summary="Offline unit-test evidence.")


def pr():
    repo = {"full_name": REPOSITORY, "default_branch": "main"}
    return {
        "number": 17, "html_url": f"https://github.com/{REPOSITORY}/pull/17", "state": "open",
        "title": "Verified HIP migration", "body": "Offline test fixture.",
        "head": {"ref": BRANCH, "sha": COMMIT, "repo": repo},
        "base": {"ref": "main", "sha": SOURCE, "repo": repo},
    }


class FakeGitHub:
    def __init__(self, *, existing=False, conflict=False, invalid_confirmation=False, failure=None):
        self.calls = []
        self.existing = existing
        self.conflict = conflict
        self.invalid_confirmation = invalid_confirmation
        self.failure = failure

    def request(self, method, path, payload=None, **kwargs):
        self.calls.append((method, path, payload))
        if self.failure:
            raise self.failure
        if path == f"/repos/{REPOSITORY}":
            return {"full_name": REPOSITORY, "default_branch": "main"}
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": SOURCE}}
        if path.endswith("/git/commits/" + SOURCE):
            return {"sha": SOURCE, "tree": {"sha": TREE}, "parents": [], "message": "source"}
        if path.endswith("/git/blobs"):
            return {"sha": BLOB}
        if path.endswith("/git/trees"):
            return {"sha": CHANGED_TREE}
        if "/git/ref/heads/" in path:
            return {"object": {"sha": COMMIT}} if self.existing else None
        if path.endswith("/git/commits/" + COMMIT):
            return {"sha": COMMIT, "tree": {"sha": TREE if self.conflict else CHANGED_TREE},
                    "parents": [{"sha": SOURCE}], "message": f"Port verified extension to ROCm for {JOB}"}
        if path.endswith("/git/commits"):
            return {"sha": COMMIT}
        if path.endswith("/git/refs"):
            return {"object": {"sha": COMMIT}}
        if "/pulls?" in path:
            return [pr()] if self.existing else []
        if path.endswith("/pulls/17"):
            value = pr()
            if self.invalid_confirmation:
                value["head"]["sha"] = "f" * 40
            return value
        if path.endswith("/pulls"):
            return pr()
        raise AssertionError((method, path, payload))


class TestPublication(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "csrc").mkdir()
        (root / "csrc/kernel.cu").write_text("// HIP source\n", encoding="utf-8")
        contents = (root / "csrc/kernel.cu").read_bytes()
        self.context = SimpleNamespace(
            workdir=root, source_subdir="fixtures/golden-repo-01", source_remote=f"https://github.com/{REPOSITORY}.git",
            source_commit=SOURCE, request=JobCreateRequest(repo_path="fixture"),
            changed_files=("csrc/kernel.cu",), verification_sha256={"csrc/kernel.cu": hashlib.sha256(contents).hexdigest()},
            verified=True,
        )

    def test_publishes_only_verified_source_and_confirms_real_pr(self):
        client = FakeGitHub()
        result = approval.publish_pull_request(self.context, report(), client)
        self.assertEqual(result.number, 17)
        self.assertEqual(client.calls[-1][:2], ("GET", f"/repos/{REPOSITORY}/pulls/17"))
        tree_payload = next(payload for method, path, payload in client.calls if path.endswith("/git/trees"))
        self.assertEqual(tree_payload["tree"][0]["path"], "fixtures/golden-repo-01/csrc/kernel.cu")
        refs = [payload for method, path, payload in client.calls if path.endswith("/git/refs")]
        self.assertEqual(refs, [{"ref": "refs/heads/" + BRANCH, "sha": COMMIT}])

    def test_retry_reuses_identical_branch_and_existing_pr(self):
        client = FakeGitHub(existing=True)
        approval.publish_pull_request(self.context, report(), client)
        self.assertFalse(any(method == "POST" and path.endswith(("/git/commits", "/git/refs", "/pulls")) for method, path, _ in client.calls))

    def test_conflicting_branch_is_never_overwritten(self):
        client = FakeGitHub(existing=True, conflict=True)
        with self.assertRaisesRegex(approval.ApprovalError, "unrelated"):
            approval.publish_pull_request(self.context, report(), client)
        self.assertFalse(any(path.endswith("/pulls") for _, path, _ in client.calls))

    def test_pr_metadata_without_matching_confirmation_is_rejected(self):
        with self.assertRaisesRegex(approval.ApprovalError, "expected open"):
            approval.publish_pull_request(self.context, report(), FakeGitHub(invalid_confirmation=True))

    def test_changed_source_after_verification_rejected_before_network(self):
        (self.context.workdir / "csrc/kernel.cu").write_text("// changed\n")
        client = FakeGitHub()
        with self.assertRaisesRegex(approval.ApprovalError, "after GPU verification"):
            approval.publish_pull_request(self.context, report(), client)
        self.assertEqual(client.calls, [])

    def test_unverified_changed_file_and_path_escape_rejected(self):
        for path in ("csrc/unknown.cu", "../credential.key"):
            self.context.changed_files = (path,)
            with self.subTest(path=path), self.assertRaises(approval.ApprovalError):
                approval.publish_pull_request(self.context, report(), FakeGitHub())

    def test_unsafe_remote_and_branch_rejected(self):
        for remote in ("https://token@github.com/owner/project", "https://example.com/owner/project", "file:///repo"):
            with self.subTest(remote=remote), self.assertRaises(approval.ApprovalError):
                approval._repository_name(remote)
        for branch in ("../main", "main.lock", "--force", "main; id", "main..old"):
            with self.subTest(branch=branch), self.assertRaises(approval.ApprovalError):
                approval._branch_name(branch, JOB)

    def test_missing_credentials_do_not_fallback_to_another_identity(self):
        with patch.dict(os.environ, {"ROCMIGRATOR_GITHUB_TOKEN": ""}), self.assertRaisesRegex(approval.ApprovalError, "ROCMIGRATOR_GITHUB_TOKEN"):
            approval.GitHubClient()

    def test_malformed_json_is_rejected(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"not json"
        with patch.dict(os.environ, {"ROCMIGRATOR_GITHUB_TOKEN": "test-only"}):
            client = approval.GitHubClient()
        client._opener = Mock()
        client._opener.open.return_value = response
        with self.assertRaisesRegex(approval.ApprovalError, "malformed JSON"):
            client.request("GET", "/repos/owner/project")

    def test_github_auth_failure_does_not_expose_token(self):
        with patch.dict(os.environ, {"ROCMIGRATOR_GITHUB_TOKEN": "test-secret-value"}):
            client = approval.GitHubClient()
        client._opener = Mock()
        client._opener.open.side_effect = approval.urllib.error.HTTPError("url", 403, "test-secret-value", {}, None)
        with self.assertRaises(approval.ApprovalError) as failure:
            client.request("GET", "/repos/owner/project")
        self.assertNotIn("test-secret-value", str(failure.exception))


class TestApprovalGates(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        evidence = report()
        self.context = SimpleNamespace(verified=True, job_id=JOB, verification_report=evidence)
        self.real_engine = SimpleNamespace(get_job_context=Mock(return_value=self.context), rollback_job=AsyncMock())
        self.patches = [
            patch.dict("sys.modules", {"agent_orchestrator.real_engine": self.real_engine}),
            patch.dict(engine._job_statuses, clear=True),
            patch.object(engine, "_publish", new_callable=AsyncMock),
            patch.object(approval, "publish_pull_request", return_value=approval.ConfirmedPullRequest.model_validate(pr())),
        ]
        self.started = [item.start() for item in self.patches]
        for item in self.patches:
            self.addCleanup(item.stop)
        approval._approval_locks.clear()
        engine._job_statuses[JOB] = JobStatusResponse(job_id=JOB, current_state=PipelineState.USER_APPROVAL, verification_report=evidence)

    async def test_wrong_job_never_calls_publisher(self):
        with self.assertRaises(approval.ApprovalError):
            await approval.approve_migration(JOB, ApprovalRequest(job_id="another", approved=True))
        self.started[-1].assert_not_called()

    async def test_only_user_approval_state_is_eligible(self):
        engine._job_statuses[JOB] = JobStatusResponse(job_id=JOB, current_state=PipelineState.REPORT, verification_report=report())
        with self.assertRaises(approval.ApprovalError):
            await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=True))
        self.started[-1].assert_not_called()

    async def test_report_must_match_real_runner_evidence(self):
        self.context.verification_report = report("another-job")
        with self.assertRaises(approval.ApprovalError):
            await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=True))
        self.started[-1].assert_not_called()

    async def test_simulation_or_missing_real_provenance_fails_closed(self):
        for context in (None, SimpleNamespace(verified=False)):
            self.real_engine.get_job_context.return_value = context
            with self.subTest(context=context), self.assertRaises(approval.ApprovalError):
                await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=True))
        self.started[-1].assert_not_called()

    async def test_rejection_rolls_back_without_publication(self):
        await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=False))
        self.real_engine.rollback_job.assert_awaited_once()
        self.started[-1].assert_not_called()

    async def test_failed_publication_keeps_verified_job_pending(self):
        self.started[-1].side_effect = approval.ApprovalError("GitHub unavailable")
        original = engine._job_statuses[JOB]
        with self.assertRaisesRegex(approval.ApprovalError, "GitHub unavailable"):
            await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=True))
        self.assertEqual(engine._job_statuses[JOB], original)

    async def test_missing_report_or_insufficient_coverage_rejected(self):
        full = report()
        small = VerificationReport(job_id=JOB, overall_status="VERIFIED", cpu_reference_verified=True, determinism_passed=True,
                                   results=[full.results[0]], total_tests=1, passed_tests=1, failed_tests=0, summary="unit fixture")
        for value in (None, small):
            engine._job_statuses[JOB] = JobStatusResponse(job_id=JOB, current_state=PipelineState.USER_APPROVAL, verification_report=value)
            with self.subTest(value=value), self.assertRaises(approval.ApprovalError):
                await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=True))
        self.started[-1].assert_not_called()

    async def test_simultaneous_approval_is_rejected(self):
        lock = asyncio.Lock()
        approval._approval_locks[JOB] = lock
        async with lock:
            with self.assertRaisesRegex(approval.ApprovalError, "already"):
                await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=True))
        self.started[-1].assert_not_called()

    async def test_transition_requires_confirmed_pr(self):
        # The production engine explicitly permits this transition only after this handler.
        with patch.dict(engine._ALLOWED_TRANSITIONS, {PipelineState.USER_APPROVAL: frozenset((PipelineState.PR_CREATED, PipelineState.ROLLED_BACK))}):
            result = await approval.approve_migration(JOB, ApprovalRequest(job_id=JOB, approved=True))
        self.assertEqual(result.current_state, PipelineState.PR_CREATED)
        self.assertEqual(result.verification_report, report().model_copy(update={"timestamp": result.verification_report.timestamp}))
        self.started[-1].assert_called_once()


class TestApprovalRoute(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.snapshot = JobStatusResponse(job_id=JOB, current_state=PipelineState.USER_APPROVAL, verification_report=report())

    def test_approval_keeps_existing_frontend_response_contract(self):
        with patch.object(routes, "get_engine_migration_status", return_value=self.snapshot), patch.object(routes, "approve_migration", new_callable=AsyncMock) as handler:
            payload = {"job_id": JOB, "approved": True, "comments": "Explicit test approval"}
            response = self.client.post(f"/api/jobs/{JOB}/approve", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        handler.assert_awaited_once_with(JOB, ApprovalRequest(**payload))

    def test_publication_failure_is_reported_without_success_response(self):
        with patch.object(routes, "get_engine_migration_status", return_value=self.snapshot), patch.object(routes, "approve_migration", new_callable=AsyncMock, side_effect=approval.ApprovalError("GitHub authentication failed.")):
            response = self.client.post(f"/api/jobs/{JOB}/approve", json={"job_id": JOB, "approved": True})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "GitHub authentication failed."})

    def test_mismatched_job_never_reaches_approval_handler(self):
        with patch.object(routes, "get_engine_migration_status", return_value=self.snapshot), patch.object(routes, "approve_migration", new_callable=AsyncMock) as handler:
            response = self.client.post(f"/api/jobs/{JOB}/approve", json={"job_id": "other", "approved": True})
        self.assertEqual(response.status_code, 409)
        handler.assert_not_called()
