"""Regression coverage for strict, immutable orchestration contracts."""

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from inspect import getmembers, isclass
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel, ValidationError

from contracts import api_schemas, patch_schemas, state_schemas, verification_schemas
from contracts.api_schemas import (
    ApprovalRequest,
    JobCreateRequest,
    JobStatusResponse,
    LogEvent,
    PRPayload,
)
from contracts.patch_schemas import PatchProposal, PatchValidationResult
from contracts.state_schemas import (
    PipelineState,
    StateTransitionEvent,
    StateTransitionRequest,
)
from contracts.verification_schemas import NumericalResult, VerificationReport


def numerical_result(**changes):
    values = {
        "seed": 42,
        "shape": [128, 64],
        "dtype": "float32",
        "atol": 1e-5,
        "rtol": 1e-5,
        "max_abs_err": 0.0,
        "max_rel_err": 0.0,
        "mismatch_ratio": 0.0,
        "nan_inf_detected": False,
        "passed": True,
    }
    values.update(changes)
    return NumericalResult(**values)


def verification_report(**changes):
    values = {
        "job_id": "job-001",
        "overall_status": "VERIFIED",
        "cpu_reference_verified": True,
        "determinism_passed": True,
        "results": [numerical_result()],
        "total_tests": 1,
        "passed_tests": 1,
        "failed_tests": 0,
        "summary": "One numerical comparison passed.",
    }
    values.update(changes)
    return VerificationReport(**values)


def patch_proposal(**changes):
    values = {
        "patch_id": "patch-001",
        "file_path": "csrc/elementwise.cu",
        "diff": (
            "--- a/csrc/elementwise.cu\n+++ b/csrc/elementwise.cu\n"
            "@@ -1 +1 @@\n-#include <cuda_runtime.h>\n+#include <hip/hip_runtime.h>\n"
        ),
        "fingerprint_id": "FP_CUDA_HEADER",
        "lines_added": 1,
        "lines_deleted": 1,
        "explanation": "Replace the CUDA runtime include with its HIP counterpart.",
    }
    values.update(changes)
    return PatchProposal(**values)


def log_event(data):
    return LogEvent(
        job_id="job-001",
        state=PipelineState.ANALYSIS,
        message="Recorded deterministic handler output.",
        data=data,
    )


class TestContractStrictness(unittest.TestCase):
    def test_all_models_expose_strict_frozen_config_and_field_guidance(self):
        modules = (state_schemas, patch_schemas, verification_schemas, api_schemas)
        for module in modules:
            for name, model in getmembers(module, isclass):
                if not issubclass(model, BaseModel) or model.__module__ != module.__name__:
                    continue
                with self.subTest(model=name):
                    self.assertIs(model.model_config.get("strict"), True)
                    self.assertIs(model.model_config.get("frozen"), True)
                    self.assertEqual(model.model_config.get("extra"), "forbid")
                for field_name, field in model.model_fields.items():
                    with self.subTest(model=name, field=field_name):
                        self.assertIsInstance(field.description, str)
                        self.assertTrue(field.description.strip())
                        self.assertTrue(field.examples)

    def test_integer_fields_reject_strings_floats_and_booleans(self):
        for value in ("2", 2.0, True):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    JobCreateRequest(repo_path="fixtures/golden-repo-01", max_repair_rounds=value)
                with self.assertRaises(ValidationError):
                    patch_proposal(lines_added=value)
                with self.assertRaises(ValidationError):
                    numerical_result(seed=value)

    def test_boolean_fields_reject_string_and_integer_substitutes(self):
        for value in ("true", "false", 1, 0):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    ApprovalRequest(job_id="job-001", approved=value)
                with self.assertRaises(ValidationError):
                    patch_proposal(modifies_dependencies=value)

    def test_unknown_top_level_and_nested_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            JobCreateRequest(repo_path="fixtures/golden-repo-01", invented_option=True)
        with self.assertRaises(ValidationError):
            StateTransitionRequest(
                job_id="job-001",
                target_state=PipelineState.CLONING,
                metadata={"shell_command": "invented"},
            )
        with self.assertRaises(ValidationError):
            log_event({"invented_measurement": 12})
        with self.assertRaises(ValidationError):
            log_event({"avg_latency_ms": 2.0, "throughput_elements_per_sec": 100.0, "invented": True})

    def test_models_and_nested_metadata_are_frozen(self):
        request = StateTransitionRequest(
            job_id="job-001",
            target_state=PipelineState.CLONING,
            metadata={"job_id": "job-001", "target_branch": "hip-port"},
        )
        with self.assertRaises(ValidationError):
            request.job_id = "job-002"
        with self.assertRaises(ValidationError):
            request.metadata.target_branch = "other-branch"
        proposal = patch_proposal()
        with self.assertRaises(ValidationError):
            proposal.lines_added = 121

    def test_nested_collections_cannot_change_after_validation(self):
        dimensions = [128, 64]
        result = numerical_result(shape=dimensions)
        results = [result]
        report = verification_report(results=results)
        paths = ["csrc/elementwise.cu"]
        event = log_event({"cu_files": paths, "total_loc": 50, "setup_path": "setup.py"})
        dimensions.append(999)
        results.clear()
        paths.append("csrc/invented.cu")
        self.assertEqual(result.shape, (128, 64))
        self.assertEqual(report.results, (result,))
        self.assertEqual(event.data.cu_files, ("csrc/elementwise.cu",))
        with self.assertRaises(TypeError):
            result.shape[0] = 999
        with self.assertRaises(TypeError):
            report.results[0] = numerical_result(seed=100)
        with self.assertRaises(TypeError):
            event.data.cu_files[0] = "csrc/invented.cu"
        with self.assertRaises(ValidationError):
            report.results[0].passed = False

    def test_python_requires_enum_instances_but_json_accepts_enum_values(self):
        with self.assertRaises(ValidationError):
            StateTransitionRequest(job_id="job-001", target_state="CLONING")
        request = StateTransitionRequest.model_validate_json(
            '{"job_id":"job-001","target_state":"CLONING"}'
        )
        self.assertIs(request.target_state, PipelineState.CLONING)
        with self.assertRaises(ValidationError):
            StateTransitionRequest.model_validate_json(
                '{"job_id":"job-001","target_state":"INVENTED"}'
            )

    def test_python_requires_datetime_instances_but_json_accepts_iso_timestamps(self):
        values = {
            "job_id": "job-001",
            "from_state": PipelineState.CREATED,
            "to_state": PipelineState.CLONING,
            "timestamp": "2026-09-21T10:00:00Z",
        }
        with self.assertRaises(ValidationError):
            StateTransitionEvent(**values)
        event = StateTransitionEvent.model_validate_json(json.dumps(values))
        self.assertEqual(event.timestamp, datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc))
        report = verification_report()
        self.assertEqual(VerificationReport.model_validate_json(report.model_dump_json()), report)
        with self.assertRaises(ValidationError):
            VerificationReport.model_validate(json.loads(report.model_dump_json()))


class TestTypedPayloadCompatibility(unittest.TestCase):
    def test_transition_metadata_cannot_refer_to_a_different_job(self):
        for nested_job_id in ("job-001", None):
            request = StateTransitionRequest(
                job_id="job-001",
                target_state=PipelineState.CLONING,
                metadata={"job_id": nested_job_id},
            )
            self.assertEqual(request.metadata.job_id, nested_job_id)
        with self.assertRaisesRegex(ValidationError, "requested job"):
            StateTransitionRequest(
                job_id="job-001",
                target_state=PipelineState.CLONING,
                metadata={"job_id": "job-002"},
            )

    def test_status_report_cannot_refer_to_a_different_job(self):
        report = verification_report()
        status = JobStatusResponse(
            job_id="job-001",
            current_state=PipelineState.REPORT,
            verification_report=report,
        )
        self.assertEqual(status.verification_report.job_id, status.job_id)
        with self.assertRaisesRegex(ValidationError, "requested job"):
            JobStatusResponse(
                job_id="job-002",
                current_state=PipelineState.REPORT,
                verification_report=report,
            )

    def test_nested_patch_instances_are_revalidated_at_the_log_boundary(self):
        proposal = patch_proposal()
        self.assertEqual(log_event(proposal).data, proposal)
        unvalidated_proposals = (
            PatchProposal.model_construct(
                **{**proposal.model_dump(), "modifies_dependencies": True}
            ),
            proposal.model_copy(update={"modifies_public_api": True}),
            proposal.model_copy(update={"modifies_tests_or_tolerances": "false"}),
        )
        for unvalidated in unvalidated_proposals:
            with self.subTest(proposal=unvalidated), self.assertRaises(ValidationError):
                log_event(unvalidated)

    def test_every_existing_log_payload_roundtrips_without_wire_changes(self):
        payloads = (
            {},
            None,
            {"cu_files": ["csrc/elementwise.cu"], "total_loc": 50, "setup_path": "setup.py"},
            patch_proposal().model_dump(mode="json"),
            {"avg_latency_ms": 2.5, "throughput_elements_per_sec": 400000.0},
            {"title": "Port extension to HIP", "body": "Verification passed.", "branch": "hip-port"},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                event = log_event(payload)
                encoded = event.model_dump_json()
                self.assertEqual(json.loads(encoded)["data"], payload)
                self.assertEqual(LogEvent.model_validate_json(encoded), event)

    def test_payload_values_are_strictly_validated(self):
        invalid_payloads = (
            {"cu_files": [1], "total_loc": 50, "setup_path": "setup.py"},
            {"cu_files": ["csrc/elementwise.cu"], "total_loc": "50", "setup_path": "setup.py"},
            {"avg_latency_ms": "2.5", "throughput_elements_per_sec": 400000.0},
            {"title": "Port extension to HIP", "body": 123, "branch": "hip-port"},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                log_event(payload)

    def test_status_repair_budget_and_approval_gate(self):
        for used in (-1, 7):
            with self.subTest(used=used), self.assertRaises(ValidationError):
                JobStatusResponse(job_id="job-001", current_state=PipelineState.REPAIR, repair_rounds_used=used)
        for approval in (False, "true", 1):
            with self.subTest(approval=approval), self.assertRaises(ValidationError):
                PRPayload(job_id="job-001", approved_by_user=approval, pr_title="HIP port", pr_body="Verified.")
        self.assertTrue(
            PRPayload(job_id="job-001", approved_by_user=True, pr_title="HIP port", pr_body="Verified.").approved_by_user
        )


class TestNumericalGuardrails(unittest.TestCase):
    def test_nonfinite_and_negative_metrics_are_rejected(self):
        fields = ("atol", "rtol", "max_abs_err", "max_rel_err", "mismatch_ratio")
        for field in fields:
            for value in (float("nan"), float("inf"), float("-inf"), -0.1):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    numerical_result(**{field: value, "passed": False})
        with self.assertRaises(ValidationError):
            numerical_result(mismatch_ratio=1.1, passed=False)

    def test_shape_elements_are_strict_nonnegative_integers(self):
        for shape in ([True], ["128"], [1.5], [-1]):
            with self.subTest(shape=shape), self.assertRaises(ValidationError):
                numerical_result(shape=shape)

    def test_existing_dtype_spellings_are_preserved(self):
        for dtype in ("float32", "float64", "torch.float32", "torch.float64"):
            with self.subTest(dtype=dtype):
                self.assertEqual(numerical_result(dtype=dtype).dtype, dtype)

    def test_passed_result_cannot_contradict_observed_failure(self):
        for changes in ({"nan_inf_detected": True}, {"mismatch_ratio": 0.1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                numerical_result(**changes)

    def test_report_counts_match_actual_results(self):
        for changes in (
            {"total_tests": 2},
            {"passed_tests": 0, "failed_tests": 1},
            {"total_tests": -1},
            {"passed_tests": -1},
            {"failed_tests": -1},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                verification_report(**changes)

    def test_verified_requires_reference_determinism_and_successful_results(self):
        failed_result = numerical_result(passed=False, mismatch_ratio=1.0)
        for changes in (
            {"cpu_reference_verified": False},
            {"determinism_passed": False},
            {"results": [], "total_tests": 0, "passed_tests": 0},
            {"results": [failed_result], "passed_tests": 0, "failed_tests": 1},
            {"overall_status": "INVENTED"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                verification_report(**changes)

    def test_unsuccessful_reports_preserve_failure_evidence(self):
        failed_result = numerical_result(passed=False, nan_inf_detected=True)
        for status in ("FAILED", "ROLLED_BACK"):
            with self.subTest(status=status):
                report = verification_report(
                    overall_status=status,
                    cpu_reference_verified=False,
                    determinism_passed=False,
                    results=[failed_result],
                    passed_tests=0,
                    failed_tests=1,
                )
                self.assertEqual(report.overall_status, status)
                self.assertTrue(report.results[0].nan_inf_detected)


class TestPatchGuardrails(unittest.TestCase):
    def test_single_patch_budget_counts_both_additions_and_deletions(self):
        self.assertEqual(patch_proposal(lines_added=60, lines_deleted=60).lines_deleted, 60)
        for added, deleted in ((60, 61), (0, 121), (121, 0)):
            with self.subTest(added=added, deleted=deleted), self.assertRaises(ValidationError):
                patch_proposal(lines_added=added, lines_deleted=deleted)

    def test_validation_result_remaining_budget_stays_in_project_bounds(self):
        for remaining in (-1, 301, "300", True):
            with self.subTest(remaining=remaining), self.assertRaises(ValidationError):
                PatchValidationResult(patch_id="patch-001", valid=False, budget_remaining=remaining)
        for remaining in (0, 300):
            self.assertEqual(
                PatchValidationResult(patch_id="patch-001", valid=False, budget_remaining=remaining).budget_remaining,
                remaining,
            )

    def test_allowlist_denials_remain_representable_for_policy_validation(self):
        proposal = patch_proposal(file_path="disallowed.sh", allowlisted=False)
        self.assertFalse(proposal.allowlisted)


class TestReportLoading(unittest.TestCase):
    def test_report_cli_loads_strict_json_and_preserves_shape_display(self):
        from scripts.generate_report import main

        with tempfile.TemporaryDirectory(prefix="contract-report-") as directory:
            directory_path = Path(directory).resolve()
            self.assertTrue(directory_path.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            json_path = directory_path / "verification_report.json"
            json_path.write_text(verification_report().model_dump_json(), encoding="utf-8")
            with patch("sys.argv", ["generate_report.py", str(json_path)]), redirect_stdout(io.StringIO()):
                main()
            html = json_path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("[128, 64]", html)
            self.assertIn("VERIFIED", html)


if __name__ == "__main__":
    unittest.main()
