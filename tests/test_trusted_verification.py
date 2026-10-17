"""Host-only harness guardrails; these tests do not establish GPU verification."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_orchestrator.torch_compat import torch as cpu_test_torch
from contracts.verification_schemas import VerificationReport

spec = importlib.util.spec_from_file_location(
    "trusted_verify_under_test", Path(__file__).resolve().parents[1] / "runner" / "verification" / "verify.py"
)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def double_tensor(values):
    constructor = getattr(cpu_test_torch, "tensor", cpu_test_torch.Tensor)
    return constructor(values, dtype=cpu_test_torch.float64)


class TrustedVerificationTests(unittest.TestCase):
    def test_rejects_malformed_job_identifiers(self):
        for value in ("", "../job", "job;true", "job\nother", "-argument", "a" * 129):
            with self.subTest(value=value), self.assertRaises(ValueError):
                harness.validate_job_id(value)
        harness.validate_job_id("job-0123_abcd")

    def test_cpu_only_environment_cannot_pass_gpu_preflight(self):
        fake_torch = types.SimpleNamespace(version=types.SimpleNamespace(hip=None))
        with self.assertRaisesRegex(RuntimeError, "CPU fallback"):
            harness.require_gpu(fake_torch)

    def test_wrong_gpu_architecture_is_rejected(self):
        fake_torch = types.SimpleNamespace(version=types.SimpleNamespace(hip="test-only"), cuda=types.SimpleNamespace(
            is_available=lambda: True, device_count=lambda: 1,
            get_device_properties=lambda _: types.SimpleNamespace(gcnArchName="gfx90a")))
        with self.assertRaisesRegex(RuntimeError, "gfx942"):
            harness.require_gpu(fake_torch)

    def test_python_module_cannot_replace_compiled_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "fused_elementwise_cuda.py").write_text("raise AssertionError('must never import')")
            with self.assertRaisesRegex(RuntimeError, "compiled"):
                harness.load_extension(root)

    def test_unavailable_torch_produces_failed_empty_report(self):
        with patch.dict(sys.modules, {"torch": None}):
            report = harness.verify("unavailable-torch")
        self.assertEqual(report.overall_status, "FAILED")
        self.assertFalse(report.cpu_reference_verified)
        self.assertFalse(report.determinism_passed)
        self.assertEqual(report.total_tests, 0)
        self.assertIn("ModuleNotFoundError", report.summary)
        self.assertEqual(VerificationReport.model_validate_json(report.model_dump_json()), report)

    def test_actual_combined_elementwise_tolerance_is_used(self):
        # Each element passes atol+rtol*abs(reference), although neither global
        # max-absolute nor global max-relative alone is sufficient here.
        expected = double_tensor([0.0, 100.0])
        actual = double_tensor([0.9e-7, 100.000009])
        result = harness.compare_case(cpu_test_torch, actual, expected,
                                      seed=42, shape=(2,), dtype="torch.float64")
        self.assertEqual(result.atol, 1e-7)
        self.assertEqual(result.rtol, 1e-7)
        self.assertTrue(result.passed)
        self.assertEqual(result.mismatch_ratio, 0.0)

    def test_one_element_outside_tolerance_fails(self):
        expected = double_tensor([0.0, 100.0])
        actual = double_tensor([2e-7, 100.0])
        result = harness.compare_case(cpu_test_torch, actual, expected,
                                      seed=42, shape=(2,), dtype="torch.float64")
        self.assertFalse(result.passed)
        self.assertEqual(result.mismatch_ratio, 0.5)

    def test_nonfinite_metrics_are_never_fabricated_as_zero(self):
        expected = double_tensor([1.0])
        for value in (float("nan"), float("inf")):
            actual = double_tensor([value])
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "NaN/Inf"):
                harness.compare_case(cpu_test_torch, actual, expected,
                                     seed=42, shape=(1,), dtype="torch.float64")

    def test_output_path_cannot_escape_workspace(self):
        with self.assertRaisesRegex(ValueError, "fixed"):
            harness.main(["job-id", "/tmp/report.json"])


if __name__ == "__main__":
    unittest.main()
