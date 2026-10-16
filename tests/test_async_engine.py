"""Behavioral coverage for the bounded, simulated asynchronous pipeline."""

import asyncio
import json
import unittest
from itertools import groupby
from unittest.mock import AsyncMock, patch

from agent_orchestrator import engine
from contracts.api_schemas import AnalysisLogData, JobCreateRequest, JobStatusResponse, LogEvent
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import NumericalResult, VerificationReport
from tests._openai_stub import install_offline_patch_client


def compile_failure(job_id, message="Simulated compiler error: threads = 32"):
    return LogEvent(
        job_id=job_id,
        state=PipelineState.COMPILING,
        level="ERROR",
        message=message,
    )


def verified_report(job_id):
    results = [
        NumericalResult(
            seed=seed,
            shape=shape,
            dtype=dtype,
            atol=1e-5,
            rtol=1e-5,
            max_abs_err=0.0,
            max_rel_err=0.0,
            mismatch_ratio=0.0,
            nan_inf_detected=False,
            passed=True,
        )
        for seed, shape, dtype in ((42, [8], "float32"), (43, [16], "float64"))
    ]
    return VerificationReport(
        job_id=job_id,
        overall_status="VERIFIED",
        cpu_reference_verified=True,
        determinism_passed=True,
        results=results,
        total_tests=2,
        passed_tests=2,
        failed_tests=0,
        summary="Injected verification evidence for the approval-boundary test.",
    )


class TestAsyncMigrationEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.create_completion = install_offline_patch_client(self)
        status_store = patch.dict(engine._job_statuses, clear=True)
        status_store.start()
        self.addCleanup(status_store.stop)
        broadcast = patch.object(engine.log_streamer, "broadcast", new_callable=AsyncMock)
        self.broadcast = broadcast.start()
        self.addCleanup(broadcast.stop)
        self.request = JobCreateRequest(repo_path="uninspected/mock/repository")

    def events(self, job_id):
        return [
            call.args[0]
            for call in self.broadcast.await_args_list
            if call.args[0].job_id == job_id
        ]

    def states(self, job_id):
        return [state for state, _ in groupby(event.state for event in self.events(job_id))]

    def proposal_override(self, **changes):
        original = engine._propose_patch

        async def changed_proposal(error, fingerprint_id, source_context):
            proposal = json.loads(await original(error, fingerprint_id, source_context))
            proposal.update(changes)
            return json.dumps(proposal)

        return patch.object(engine, "_propose_patch", side_effect=changed_proposal)

    async def test_default_repair_rolls_back_without_real_verification(self):
        job_id = "async-default"
        result = await engine.run_migration_pipeline(job_id, self.request)
        self.create_completion.assert_awaited_once()
        self.assertIsInstance(result, JobStatusResponse)
        self.assertEqual(JobStatusResponse.model_validate_json(result.model_dump_json()), result)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.repair_rounds_used, 1)
        self.assertIsNone(result.best_known_commit)
        self.assertEqual(engine.get_migration_status(job_id), result)
        report = result.verification_report
        self.assertIsInstance(report, VerificationReport)
        self.assertEqual(report.job_id, job_id)
        self.assertEqual(report.overall_status, "FAILED")
        self.assertFalse(report.cpu_reference_verified)
        self.assertFalse(report.determinism_passed)
        self.assertEqual(report.results, ())
        self.assertEqual(report.total_tests, 0)
        self.assertNotIn(PipelineState.PR_CREATED, self.states(job_id))

    async def test_pipeline_broadcasts_ordered_strict_events(self):
        job_id = "async-events"
        await engine.run_migration_pipeline(job_id, self.request)
        expected_prefix = [
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
        ]
        actual = self.states(job_id)
        self.assertEqual(actual[:len(expected_prefix)], expected_prefix)
        self.assertEqual(actual[-1], PipelineState.ROLLED_BACK)
        for event in self.events(job_id):
            self.assertIsInstance(event, LogEvent)
            self.assertEqual(LogEvent.model_validate_json(event.model_dump_json()), event)

    async def test_requested_repair_limit_is_honored(self):
        job_id = "async-limit"
        with patch.object(
            engine, "_run_compile_step", new_callable=AsyncMock,
            return_value=compile_failure(job_id),
        ) as compile_step:
            result = await engine.run_migration_pipeline(
                job_id, JobCreateRequest(repo_path="mock", max_repair_rounds=1)
            )
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.repair_rounds_used, 1)
        self.assertEqual(compile_step.await_count, 2)
        self.assertEqual(engine.MAX_REPAIRS, 3)

    async def test_repeated_error_stops_after_two_unsuccessful_repairs(self):
        job_id = "async-stalled"
        with patch.object(
            engine, "_run_compile_step", new_callable=AsyncMock,
            return_value=compile_failure(job_id),
        ) as compile_step, patch.object(
            engine, "_propose_patch", wraps=engine._propose_patch
        ) as propose, patch.object(
            engine, "_run_verification_step", new_callable=AsyncMock
        ) as verify:
            result = await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.repair_rounds_used, 2)
        self.assertEqual(propose.await_count, 2)
        self.assertEqual(compile_step.await_count, 3)
        verify.assert_not_awaited()

    async def test_deterministic_header_errors_are_not_sent_to_patch_proposer(self):
        job_id = "async-header-error"
        with patch.object(
            engine, "_run_compile_step", new_callable=AsyncMock,
            return_value=compile_failure(job_id, "fatal error: cuda_runtime.h not found"),
        ), patch.object(engine, "_propose_patch", new_callable=AsyncMock) as propose:
            result = await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        propose.assert_not_awaited()

    async def test_three_round_hard_cap_applies_even_while_error_set_improves(self):
        job_id = "async-hard-cap"
        errors = [
            compile_failure(
                job_id,
                "\n".join(f"error: simulated failure {index}: threads = 32" for index in range(count)),
            )
            for count in (3, 2, 1, 1)
        ]
        # Isolate the independent round limit from the stricter fingerprint limit.
        with patch.object(
            engine.FingerprintDB, "record_occurrence", return_value=True
        ), patch.object(
            engine, "_run_compile_step", new_callable=AsyncMock, side_effect=errors
        ) as compile_step, patch.object(
            engine, "_propose_patch", wraps=engine._propose_patch
        ) as propose:
            result = await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.repair_rounds_used, 3)
        self.assertEqual(propose.await_count, 3)
        self.assertEqual(compile_step.await_count, 4)

    async def test_fingerprint_limit_stops_repairs_despite_measured_progress(self):
        job_id = "async-fingerprint-limit"
        errors = [
            compile_failure(
                job_id,
                "\n".join(f"error: simulated failure {index}: threads = 32" for index in range(count)),
            )
            for count in (3, 2, 1)
        ]
        with patch.object(
            engine, "_run_compile_step", new_callable=AsyncMock, side_effect=errors
        ) as compile_step, patch.object(
            engine, "_propose_patch", wraps=engine._propose_patch
        ) as propose:
            result = await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.repair_rounds_used, 2)
        self.assertEqual(propose.await_count, 2)
        self.assertEqual(compile_step.await_count, 3)
        self.assertTrue(any(
            event.level == "ERROR" and "fingerprint" in event.message.lower()
            for event in self.events(job_id)
        ))

    async def test_malformed_patch_json_never_reaches_patch_checks_or_apply(self):
        with patch.object(
            engine, "_propose_patch", new_callable=AsyncMock, return_value="{invalid json"
        ) as propose, patch.object(
            engine, "_run_patch_check_step", new_callable=AsyncMock
        ) as check, patch.object(
            engine, "_run_apply_patch_step", new_callable=AsyncMock
        ) as apply:
            result = await engine.run_migration_pipeline("async-invalid-json", self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertGreaterEqual(result.repair_rounds_used, 1)
        self.assertLessEqual(propose.await_count, 2)
        check.assert_not_awaited()
        apply.assert_not_awaited()

    async def test_forbidden_flags_and_untrusted_paths_fail_before_patch_check(self):
        invalid_changes = [
            {"modifies_dependencies": True},
            {"modifies_public_api": True},
            {"modifies_tests_or_tolerances": True},
            {"allowlisted": False},
            {"file_path": "../outside.cu"},
            {"file_path": "csrc/not-analyzed.cu"},
            {"fingerprint_id": "FP_INVENTED"},
            {"lines_added": "1"},
        ]
        for index, changes in enumerate(invalid_changes):
            with self.subTest(changes=changes):
                with self.proposal_override(**changes), patch.object(
                    engine, "_run_patch_check_step", new_callable=AsyncMock
                ) as check, patch.object(
                    engine, "_run_apply_patch_step", new_callable=AsyncMock
                ) as apply:
                    result = await engine.run_migration_pipeline(f"async-rejected-{index}", self.request)
                self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
                check.assert_not_awaited()
                apply.assert_not_awaited()

    async def test_declared_line_counts_are_derived_after_applicability(self):
        with self.proposal_override(lines_added=12, lines_deleted=1), patch.object(
            engine, "_run_patch_check_step", wraps=engine._run_patch_check_step
        ) as check, patch.object(
            engine, "_run_apply_patch_step", wraps=engine._run_apply_patch_step
        ) as apply:
            result = await engine.run_migration_pipeline("async-derived-counts", self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.verification_report.overall_status, "FAILED")
        check.assert_awaited_once()
        apply.assert_awaited_once()
        self.assertEqual(check.await_args.args[1].lines_added, 12)
        accepted = apply.await_args.args[1]
        self.assertEqual((accepted.lines_added, accepted.lines_deleted), (1, 1))
        self.assertEqual(accepted.diff, engine._SIM_DIFF)
        self.assertIn(PipelineState.VERIFYING, self.states(result.job_id))

    async def test_cumulative_cuda_line_budget_blocks_second_application(self):
        job_id = "async-cumulative-budget"
        analysis = AnalysisLogData(
            cu_files=("csrc/elementwise.cu",), total_loc=20, setup_path="setup.py"
        )
        with patch.object(
            engine, "_run_analysis_step", new_callable=AsyncMock, return_value=analysis
        ), patch.object(
            engine, "_run_compile_step", new_callable=AsyncMock,
            return_value=compile_failure(job_id),
        ), patch.object(
            engine, "_run_patch_check_step", wraps=engine._run_patch_check_step
        ) as check, patch.object(
            engine, "_run_apply_patch_step", wraps=engine._run_apply_patch_step
        ) as apply:
            result = await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.repair_rounds_used, 2)
        self.assertEqual(check.await_count, 2)
        self.assertEqual(apply.await_count, 1)
        self.assertTrue(any(
            event.level == "ERROR" and "budget" in event.message.lower()
            for event in self.events(job_id)
        ))

    async def test_non_simulated_diff_is_not_applied(self):
        unsafe_diff = (
            "--- a/csrc/elementwise.cu\n+++ b/csrc/elementwise.cu\n"
            "@@ -1 +1 @@\n-__global__ void kernel() {}\n+// removed kernel\n"
        )
        with self.proposal_override(diff=unsafe_diff), patch.object(
            engine, "_run_apply_patch_step", new_callable=AsyncMock
        ) as apply:
            result = await engine.run_migration_pipeline("async-unsafe-diff", self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        apply.assert_not_awaited()

    async def test_mismatched_and_unvalidated_compile_results_fail_closed(self):
        outputs = [
            compile_failure("another-job"),
            LogEvent(job_id="async-invalid-hook-1", state=PipelineState.REPAIR, message="Wrong state"),
            {"job_id": "async-invalid-hook-2", "level": "INFO", "message": "Not a LogEvent"},
            LogEvent.model_construct(
                job_id="async-invalid-hook-3", state=PipelineState.COMPILING,
                level="INFO", message=123,
            ),
        ]
        for index, output in enumerate(outputs):
            with self.subTest(output=output):
                with patch.object(
                    engine, "_run_compile_step", new_callable=AsyncMock, return_value=output
                ), patch.object(engine, "_run_verification_step", new_callable=AsyncMock) as verify:
                    result = await engine.run_migration_pipeline(f"async-invalid-hook-{index}", self.request)
                self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
                verify.assert_not_awaited()

    async def test_verification_for_another_job_cannot_reach_approval(self):
        with patch.object(
            engine, "_run_verification_step", new_callable=AsyncMock,
            return_value=verified_report("another-job"),
        ):
            result = await engine.run_migration_pipeline("async-wrong-report", self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.verification_report.job_id, result.job_id)
        self.assertEqual(result.verification_report.overall_status, "ROLLED_BACK")
        self.assertFalse(result.verification_report.cpu_reference_verified)
        self.assertNotIn(PipelineState.USER_APPROVAL, self.states(result.job_id))

    async def test_verified_report_stops_at_user_approval_without_creating_pr(self):
        job_id = "async-awaiting-approval"
        with patch.object(
            engine, "_run_verification_step", new_callable=AsyncMock,
            return_value=verified_report(job_id),
        ):
            result = await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(result.current_state, PipelineState.USER_APPROVAL)
        self.assertEqual(result.verification_report.overall_status, "VERIFIED")
        states = self.states(job_id)
        self.assertEqual(
            states[-4:],
            [PipelineState.VERIFYING, PipelineState.BENCHMARKING, PipelineState.REPORT, PipelineState.USER_APPROVAL],
        )
        self.assertNotIn(PipelineState.PR_CREATED, states)

    async def test_sparse_verified_evidence_cannot_reach_user_approval(self):
        job_id = "async-sparse-verification"
        full_report = verified_report(job_id)
        sparse_report = VerificationReport(**{
            **full_report.model_dump(),
            "results": full_report.results[:1],
            "total_tests": 1,
            "passed_tests": 1,
        })
        with patch.object(
            engine, "_run_verification_step", new_callable=AsyncMock, return_value=sparse_report
        ):
            result = await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertNotIn(PipelineState.USER_APPROVAL, self.states(job_id))

    async def test_concurrent_jobs_have_independent_status_and_repair_counts(self):
        first, second, third = await asyncio.gather(
            engine.run_migration_pipeline("async-first", self.request),
            engine.run_migration_pipeline("async-second", self.request),
            engine.run_migration_pipeline("async-third", self.request),
        )
        for result in (first, second, third):
            self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
            self.assertEqual(result.repair_rounds_used, 1)
            self.assertEqual(result.verification_report.job_id, result.job_id)
            self.assertEqual(engine.get_migration_status(result.job_id), result)
            self.assertTrue(self.events(result.job_id))
        self.assertEqual(len({first.job_id, second.job_id, third.job_id}), 3)
        self.assertIsNone(engine.get_migration_status("not-a-job"))

    async def test_step_timeout_records_rollback(self):
        async def blocked_hipify(job_id):
            await asyncio.Event().wait()

        with patch.object(engine, "STEP_TIMEOUT_SECONDS", 0.01), patch.object(
            engine, "_run_hipify_step", side_effect=blocked_hipify
        ):
            result = await asyncio.wait_for(
                engine.run_migration_pipeline("async-timeout", self.request), timeout=1.0
            )
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(engine.get_migration_status(result.job_id), result)
        self.assertTrue(any(event.level == "ERROR" for event in self.events(result.job_id)))

    async def test_cancellation_preserves_rollback_and_propagates(self):
        entered = asyncio.Event()

        async def blocked_hipify(job_id):
            entered.set()
            await asyncio.Event().wait()

        job_id = "async-cancelled"
        with patch.object(engine, "_run_hipify_step", side_effect=blocked_hipify):
            task = asyncio.create_task(engine.run_migration_pipeline(job_id, self.request))
            try:
                await asyncio.wait_for(entered.wait(), timeout=1.0)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(engine.get_migration_status(job_id).current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(self.states(job_id)[-1], PipelineState.ROLLED_BACK)

    async def test_duplicate_job_id_does_not_replace_running_or_completed_status(self):
        original_hipify = engine._run_hipify_step
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocked_hipify(job_id):
            entered.set()
            await release.wait()
            return await original_hipify(job_id)

        job_id = "async-duplicate"
        with patch.object(engine, "_run_hipify_step", side_effect=blocked_hipify):
            task = asyncio.create_task(engine.run_migration_pipeline(job_id, self.request))
            try:
                await asyncio.wait_for(entered.wait(), timeout=1.0)
                running = engine.get_migration_status(job_id)
                with self.assertRaises(ValueError):
                    await engine.run_migration_pipeline(job_id, self.request)
                self.assertEqual(engine.get_migration_status(job_id), running)
            finally:
                release.set()
                result = await asyncio.wait_for(task, timeout=1.0)
        with self.assertRaises(ValueError):
            await engine.run_migration_pipeline(job_id, self.request)
        self.assertEqual(engine.get_migration_status(job_id), result)

    async def test_failed_rollback_is_not_retried_or_reported_as_restored(self):
        job_id = "async-rollback-failed"

        async def failed_rollback(current):
            return LogEvent(
                job_id=current.job_id,
                state=current.current_state,
                level="ERROR",
                message="Rollback runner could not restore its checkpoint.",
            )

        with patch.object(engine, "_run_rollback_step", side_effect=failed_rollback) as rollback:
            with self.assertRaisesRegex(RuntimeError, "Rollback hook failed"):
                await engine.run_migration_pipeline(job_id, self.request)
        rollback.assert_awaited_once()
        snapshot = engine.get_migration_status(job_id)
        self.assertEqual(snapshot.current_state, PipelineState.VERIFYING)
        self.assertEqual(snapshot.verification_report.overall_status, "FAILED")
        self.assertIn("unconfirmed", snapshot.verification_report.summary)
        self.assertTrue(any(
            event.level == "ERROR" and "Rollback failed" in event.message
            for event in self.events(job_id)
        ))
        self.assertNotIn(PipelineState.ROLLED_BACK, self.states(job_id))

    async def test_rollback_exception_propagates_without_a_second_restore_attempt(self):
        job_id = "async-rollback-exception"
        failure = RuntimeError("Original runner restoration failure")
        with patch.object(
            engine, "_run_rollback_step", new_callable=AsyncMock, side_effect=failure
        ) as rollback:
            with self.assertRaises(RuntimeError) as caught:
                await engine.run_migration_pipeline(job_id, self.request)
        self.assertIs(caught.exception, failure)
        rollback.assert_awaited_once()
        snapshot = engine.get_migration_status(job_id)
        self.assertNotEqual(snapshot.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(snapshot.verification_report.overall_status, "FAILED")

    async def test_cancellation_during_terminal_broadcast_preserves_rollback(self):
        job_id = "async-terminal-cancellation"

        async def cancel_terminal_delivery(event):
            if event.state == PipelineState.ROLLED_BACK:
                raise asyncio.CancelledError

        self.broadcast.side_effect = cancel_terminal_delivery
        with patch.object(
            engine, "_run_rollback_step", wraps=engine._run_rollback_step
        ) as rollback:
            with self.assertRaises(asyncio.CancelledError):
                await engine.run_migration_pipeline(job_id, self.request)
            snapshot = engine.get_migration_status(job_id)
            self.assertEqual(snapshot.current_state, PipelineState.ROLLED_BACK)
            self.assertEqual(await engine._rollback(job_id, "Late cancellation cleanup"), snapshot)
        rollback.assert_awaited_once()

    async def test_large_compile_log_passes_only_bounded_relevant_context_to_proposer(self):
        job_id = "async-bounded-errors"
        relevant = [f"error: launch condition {index}: threads = 32" for index in range(6)]
        full_log = "\n".join(["Unrelated diagnostic output"] * 20 + relevant)
        compilation = [
            compile_failure(job_id, full_log),
            LogEvent(
                job_id=job_id, state=PipelineState.COMPILING, level="INFO",
                message="Injected successful compilation after repair.",
            ),
        ]
        with patch.object(
            engine, "_run_compile_step", new_callable=AsyncMock, side_effect=compilation
        ), patch.object(engine, "_propose_patch", wraps=engine._propose_patch) as propose:
            result = await engine.run_migration_pipeline(job_id, self.request)
        propose.assert_awaited_once()
        error, fingerprint_id, source_context = propose.await_args.args
        self.assertEqual(error.message.splitlines(), relevant[:3])
        self.assertLessEqual(len(error.message), 4000)
        self.assertEqual(fingerprint_id, "FP_WARP_SIZE")
        self.assertIsInstance(source_context, tuple)
        self.assertGreaterEqual(len(source_context), 80)
        self.assertLessEqual(len(source_context), 150)
        self.assertEqual(result.repair_rounds_used, 1)
        self.assertEqual(result.verification_report.overall_status, "FAILED")

    async def test_oversized_error_context_is_rejected_before_proposer(self):
        prefix = "error: threads = 32 "
        contexts = [
            prefix + "x" * 4000,
            "\n".join([prefix + "x" * (1333 - len(prefix))] * 3),
        ]
        for index, context in enumerate(contexts):
            with self.subTest(context_length=len(context)):
                job_id = f"async-oversized-errors-{index}"
                with patch.object(
                    engine, "_run_compile_step", new_callable=AsyncMock,
                    return_value=compile_failure(job_id, context),
                ), patch.object(engine, "_propose_patch", new_callable=AsyncMock) as propose:
                    result = await engine.run_migration_pipeline(job_id, self.request)
                propose.assert_not_awaited()
                self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)


if __name__ == "__main__":
    unittest.main()
