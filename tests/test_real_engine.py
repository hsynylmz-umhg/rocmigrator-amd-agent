"""Unit tests for real orchestration gates; injected evidence is never a GPU test."""

import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from difflib import unified_diff

from agent_orchestrator import engine, real_engine
from agent_orchestrator.runner_client import RunnerClient
from contracts.api_schemas import BenchmarkLogData, JobCreateRequest, LogEvent
from contracts.patch_schemas import PatchProposal
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import NumericalResult, VerificationReport


class RealEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "sources" / "golden-01"
        shutil.copytree(real_engine.PROJECT_ROOT / "fixtures" / "golden-repo-01", self.source,
                        ignore=shutil.ignore_patterns("__pycache__", "build", "*.so"))
        self.request = JobCreateRequest(repo_path=str(self.source))
        environment = patch.dict(os.environ, {"ROCMIGRATOR_REPOSITORY_ROOT": str(root / "sources"),
                                             "ROCMIGRATOR_JOBS_ROOT": str(root / "jobs")})
        environment.start()
        self.addCleanup(environment.stop)
        for mapping in (engine._job_statuses, real_engine._contexts):
            store = patch.dict(mapping, clear=True)
            store.start()
            self.addCleanup(store.stop)
        publisher = patch.object(engine.log_streamer, "broadcast", new_callable=AsyncMock)
        self.broadcast = publisher.start()
        self.addCleanup(publisher.stop)

    def report(self, job_id, passed=True):
        cases = tuple(NumericalResult(seed=seed, shape=shape, dtype=dtype, atol=1e-5, rtol=1e-5,
                                      max_abs_err=0.0 if passed else 1.0,
                                      max_rel_err=0.0 if passed else 1.0,
                                      mismatch_ratio=0.0 if passed else 1.0,
                                      nan_inf_detected=False, passed=passed)
                      for seed, shape, dtype in ((42, (8,), "float32"), (1337, (16,), "float64")))
        return VerificationReport(job_id=job_id, overall_status="VERIFIED" if passed else "FAILED",
                                  cpu_reference_verified=True, determinism_passed=True,
                                  results=cases, total_tests=2, passed_tests=2 if passed else 0,
                                  failed_tests=0 if passed else 2, summary="Injected unit-test runner evidence.")

    def fake_runner(self, *, report_job=None, passed=True):
        calls = []
        async def run(job_id, operation, input_dir, source=None):
            calls.append(operation)
            state = {"baseline": PipelineState.BASELINE, "hipify": PipelineState.HIPIFICATION,
                     "compile": PipelineState.COMPILING, "verify": PipelineState.VERIFYING,
                     "benchmark": PipelineState.BENCHMARKING}[operation]
            report = self.report(report_job or job_id, passed) if operation == "verify" else None
            data = BenchmarkLogData(avg_latency_ms=1.0, throughput_elements_per_sec=1000.0) if operation == "benchmark" else None
            message = (input_dir / source).read_text() if source else "Injected unit-test runner event."
            event = None if report else LogEvent(job_id=job_id, state=state, message=message, data=data)
            return SimpleNamespace(returncode=1 if operation == "verify" and not passed else 0,
                                   event=event, report=report, stdout="", stderr="", duration_seconds=0.01)
        return SimpleNamespace(run=run), calls

    def test_export_is_separate_and_checkpoint_restores_only_private_files(self):
        context = real_engine.prepare_export("real-export", self.request)
        self.assertFalse((context.workdir / ".git").exists())
        original = (self.source / "csrc/elementwise.cu").read_bytes()
        (context.workdir / "csrc/elementwise.cu").write_text("changed\n")
        self.assertEqual((self.source / "csrc/elementwise.cu").read_bytes(), original)
        self.assertTrue(context.rollback.restore_isolated_files(str(context.git_dir), context.input_files))
        self.assertEqual((context.workdir / "csrc/elementwise.cu").read_bytes(), original)

    def test_credentials_and_outside_roots_are_rejected(self):
        (self.source / ".env").write_text("not-a-real-credential")
        with self.assertRaises(ValueError):
            real_engine.prepare_export("reject-credential", self.request)
        with self.assertRaises(ValueError):
            real_engine.prepare_export("reject-outside", JobCreateRequest(repo_path=str(self.source.parent.parent)))

    def test_patch_must_apply_and_match_reviewed_policy(self):
        target = self.source / "csrc/elementwise.cu"
        target.write_text(target.read_text().replace("#include <hip/hip_runtime.h>", "#include <cuda_runtime.h>", 1), newline="\n")
        context = real_engine.prepare_export("real-patch", self.request)
        analysis = real_engine.analyze(context)
        original = (context.workdir / "csrc/elementwise.cu").read_text()
        replacement = real_engine._known_transform(original, "FP_CUDA_HEADER")
        diff = "".join(unified_diff(original.splitlines(keepends=True), replacement.splitlines(keepends=True),
                                    fromfile="a/csrc/elementwise.cu", tofile="b/csrc/elementwise.cu"))
        proposal = PatchProposal(patch_id="actual-header", file_path="csrc/elementwise.cu", diff=diff,
                                 fingerprint_id="FP_CUDA_HEADER", lines_added=1, lines_deleted=1,
                                 explanation="Replace observed unsupported CUDA runtime include.")
        self.assertEqual(real_engine.validate_patch(context, proposal.model_dump_json(), "FP_CUDA_HEADER", analysis, 0), proposal)
        for changes in ({"diff": diff.replace("-#include <cuda_runtime.h>", "-#include <missing.h>")},
                        {"file_path": "reference.py"}, {"lines_added": 0},
                        {"diff": diff.replace("+#include <hip/hip_runtime.h>", "+// kernel removed")}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, RuntimeError)):
                real_engine.validate_patch(context, json.dumps({**proposal.model_dump(), **changes}), "FP_CUDA_HEADER", analysis, 0)
        with self.assertRaises(ValueError):
            real_engine.validate_patch(context, proposal.model_dump_json(), "FP_CUDA_HEADER", analysis, 300)

    async def test_success_has_no_repair_and_stops_for_approval(self):
        runner, calls = self.fake_runner()
        with patch.object(RunnerClient, "from_environment", return_value=runner), patch.object(real_engine, "security_scan", return_value="Injected scan success."):
            result = await real_engine.run_real_pipeline("real-success", self.request)
        self.assertEqual(result.current_state, PipelineState.USER_APPROVAL)
        self.assertEqual(result.repair_rounds_used, 0)
        self.assertEqual(calls, ["baseline", "hipify", "compile", "verify", "benchmark"])
        self.assertTrue(real_engine.get_job_context("real-success").verified)
        self.assertTrue(real_engine.get_job_context("real-success").verification_sha256)
        self.assertNotIn(PipelineState.REPAIR, [call.args[0].state for call in self.broadcast.await_args_list])

    async def test_failed_verification_preserves_report_and_restores_export(self):
        runner, calls = self.fake_runner(passed=False)
        with patch.object(RunnerClient, "from_environment", return_value=runner), patch.object(real_engine, "security_scan", return_value="Injected scan success."):
            result = await real_engine.run_real_pipeline("real-failed", self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.verification_report.overall_status, "FAILED")
        self.assertEqual(result.verification_report.failed_tests, 2)
        self.assertNotIn("benchmark", calls)
        self.assertFalse(real_engine.get_job_context("real-failed").verified)

    async def test_other_job_report_and_runner_initialization_fail_closed(self):
        runner, _ = self.fake_runner(report_job="another-job")
        with patch.object(RunnerClient, "from_environment", return_value=runner), patch.object(real_engine, "security_scan", return_value="Injected scan success."):
            result = await real_engine.run_real_pipeline("real-wrong-job", self.request)
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.verification_report.job_id, "real-wrong-job")
        with patch.object(RunnerClient, "from_environment", side_effect=RuntimeError("No Docker")), patch.object(engine, "_run_simulation_pipeline", new_callable=AsyncMock) as simulation:
            result = await real_engine.run_real_pipeline("real-no-docker", self.request)
            simulation.assert_not_awaited()
        self.assertEqual(result.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(result.repair_rounds_used, 0)


if __name__ == "__main__":
    unittest.main()
