"""Trusted Golden 01 GPU verification; this directory is mounted read-only.

Never import reference.py, test_kernel.py, or Python modules from /workspace.
Only the compiled native extension is loaded from the disposable build output.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import math
import re
import stat
import sys
from pathlib import Path

sys.path.insert(0, "/opt/rocmigrator")
from contracts.verification_schemas import NumericalResult, VerificationReport

SEEDS = (42, 1337, 2026)
SHAPES = ((128, 64), (32, 128, 256), (1024,))
ALPHA = 0.01
EXTENSION = "fused_elementwise_cuda"
WORKSPACE = Path("/workspace")


def validate_job_id(job_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", job_id):
        raise ValueError("Invalid runner job identifier.")


def require_gpu(torch) -> str:
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError("A real ROCm PyTorch AMD GPU is required; CPU fallback is forbidden.")
    if torch.cuda.device_count() != 1:
        raise RuntimeError("Exactly one visible AMD GPU is required.")
    properties = torch.cuda.get_device_properties(0)
    architecture = str(getattr(properties, "gcnArchName", ""))
    if architecture.split(":", 1)[0] != "gfx942":
        raise RuntimeError(f"Golden 01 MI300X demonstration requires gfx942, received {architecture}.")
    return f"{properties.name}; {architecture}; PyTorch {torch.__version__}; ROCm {torch.version.hip}"


def load_extension(workspace: Path = WORKSPACE):
    candidates = []
    for suffix in importlib.machinery.EXTENSION_SUFFIXES:
        candidate = workspace / (EXTENSION + suffix)
        if candidate.exists():
            candidates.append(candidate)
    if len(candidates) != 1:
        raise RuntimeError("Expected exactly one compiled fused_elementwise_cuda native extension.")
    artifact = candidates[0]
    info = artifact.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 64 * 1024**2:
        raise RuntimeError("Compiled extension must be a bounded, ordinary nonlinked file.")
    spec = importlib.util.spec_from_file_location(EXTENSION, artifact)
    if spec is None or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
        raise RuntimeError("Only a compiled native extension may be verified.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "forward", None)):
        raise RuntimeError("Compiled extension does not export forward(x, bias, alpha).")
    return module


def cpu_reference(torch, x, bias):
    """Independent reviewed implementation of the fixture's CPU formula."""
    if x.device.type != "cpu" or bias.device.type != "cpu":
        raise RuntimeError("Reference inputs must reside on the CPU.")
    value = x + bias
    return torch.where(value > 0, value, value * ALPHA)


def compare_case(torch, actual, expected, *, seed: int, shape: tuple[int, ...], dtype: str) -> NumericalResult:
    atol = rtol = 1e-5 if dtype == "torch.float32" else 1e-7
    nan_inf = bool(torch.isnan(actual).any().item() or torch.isinf(actual).any().item()
                   or torch.isnan(expected).any().item() or torch.isinf(expected).any().item())
    absolute = torch.abs(actual - expected)
    max_abs = float(torch.max(absolute).item())
    max_rel = float(torch.max(absolute / (torch.abs(expected) + 1e-12)).item())
    # The immutable contract forbids nonfinite error metrics. Fail the report
    # with the explicit reason instead of replacing unrepresentable errors by 0.
    if not math.isfinite(max_abs) or not math.isfinite(max_rel):
        raise RuntimeError("NaN/Inf detected; nonfinite numerical errors cannot be represented by the report contract.")
    mismatch = float((absolute > (atol + rtol * torch.abs(expected))).sum().item()) / expected.numel()
    passed = not nan_inf and mismatch == 0.0
    try:
        torch.testing.assert_close(actual, expected, atol=atol, rtol=rtol)
    except AssertionError:
        passed = False
    return NumericalResult(seed=seed, shape=shape, dtype=dtype, atol=atol, rtol=rtol,
                           max_abs_err=max_abs, max_rel_err=max_rel, mismatch_ratio=mismatch,
                           nan_inf_detected=nan_inf, passed=passed)


def verify(job_id: str) -> VerificationReport:
    validate_job_id(job_id)
    results = []
    failures = []
    determinism = True
    hardware = "GPU preflight did not complete"
    try:
        import torch
        hardware = require_gpu(torch)
        extension = load_extension()
        with torch.inference_mode():
            for seed in SEEDS:
                torch.manual_seed(seed)
                for shape in SHAPES:
                    for dtype in (torch.float32, torch.float64):
                        x_cpu = torch.randn(shape, dtype=dtype, device="cpu")
                        bias_cpu = torch.randn((shape[-1],), dtype=dtype, device="cpu")
                        expected = cpu_reference(torch, x_cpu, bias_cpu)
                        x, bias = x_cpu.to("cuda"), bias_cpu.to("cuda")
                        output = extension.forward(x, bias, ALPHA)
                        torch.cuda.synchronize()
                        if not isinstance(output, torch.Tensor) or not output.is_cuda:
                            raise RuntimeError("Compiled extension returned a non-GPU result.")
                        if output.shape != x.shape or output.dtype != dtype:
                            raise RuntimeError("Compiled extension changed output shape or dtype.")
                        actual = output.cpu()
                        results.append(compare_case(torch, actual, expected, seed=seed, shape=shape, dtype=str(dtype)))
                        for _ in range(3):
                            repeated = extension.forward(x, bias, ALPHA)
                            torch.cuda.synchronize()
                            if not isinstance(repeated, torch.Tensor) or not repeated.is_cuda:
                                raise RuntimeError("Determinism execution returned a non-GPU result.")
                            determinism = bool(torch.equal(actual, repeated.cpu())) and determinism
    except Exception as error:
        failures.append(f"{type(error).__name__}: {str(error)[:1000]}")
        determinism = False
    passed = sum(result.passed for result in results)
    complete = len(results) == len(SEEDS) * len(SHAPES) * 2
    success = complete and passed == len(results) and determinism and not failures
    summary = (f"Golden 01: {passed}/{len(results)} completed comparisons passed; "
               f"18 required cases; determinism {'passed' if determinism and complete else 'failed or incomplete'}. "
               f"Hardware: {hardware}. " + " ".join(failures))
    return VerificationReport(job_id=job_id, overall_status="VERIFIED" if success else "FAILED",
                              cpu_reference_verified=complete and passed == len(results),
                              determinism_passed=determinism and complete, results=tuple(results),
                              total_tests=len(results), passed_tests=passed,
                              failed_tests=len(results) - passed, summary=summary)


def main(arguments: list[str]) -> int:
    if len(arguments) != 2:
        raise ValueError("Usage: verify.py JOB_ID /workspace/verification_report.json")
    job_id, output_path = arguments
    if Path(output_path) != WORKSPACE / "verification_report.json":
        raise ValueError("Verification output path is fixed.")
    report = verify(job_id)
    with Path(output_path).open("x", encoding="utf-8") as output:
        output.write(report.model_dump_json())
    # A completed FAILED report is valid evidence; the supervisor sets exit=1.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
