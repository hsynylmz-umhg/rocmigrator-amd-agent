"""Trusted, synchronized MI300X kernel latency measurement for Golden 01."""

from __future__ import annotations

import importlib.util
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/rocmigrator")
from contracts.api_schemas import BenchmarkLogData, LogEvent
from contracts.state_schemas import PipelineState

# Load only the sibling from the trusted read-only mount under isolated Python.
spec = importlib.util.spec_from_file_location("trusted_golden_verification", Path(__file__).with_name("verify.py"))
trusted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trusted)


def benchmark(job_id: str) -> LogEvent:
    import torch
    trusted.validate_job_id(job_id)
    hardware = trusted.require_gpu(torch)
    extension = trusted.load_extension()
    shape = (32, 128, 256)
    warmup, iterations = 20, 100
    with torch.inference_mode():
        torch.manual_seed(42)
        x_cpu = torch.randn(shape, dtype=torch.float32, device="cpu")
        bias_cpu = torch.randn((shape[-1],), dtype=torch.float32, device="cpu")
        x, bias = x_cpu.to("cuda"), bias_cpu.to("cuda")
        for _ in range(warmup):
            output = extension.forward(x, bias, trusted.ALPHA)
        torch.cuda.synchronize()
        if not isinstance(output, torch.Tensor) or not output.is_cuda:
            raise RuntimeError("Benchmark requires an actual GPU output.")
        # Recheck the measured case before reporting performance.
        torch.testing.assert_close(output.cpu(), trusted.cpu_reference(torch, x_cpu, bias_cpu), atol=1e-5, rtol=1e-5)
        torch.cuda.synchronize()
        started = time.perf_counter_ns()
        for _ in range(iterations):
            output = extension.forward(x, bias, trusted.ALPHA)
        torch.cuda.synchronize()
        elapsed_seconds = (time.perf_counter_ns() - started) / 1e9
        if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
            raise RuntimeError("GPU timing did not produce a positive finite duration.")
        # Host wall time includes launch overhead and synchronization, and is
        # explicitly labeled rather than misrepresented as kernel-only events.
        data = BenchmarkLogData(avg_latency_ms=elapsed_seconds * 1000 / iterations,
                                throughput_elements_per_sec=x.numel() * iterations / elapsed_seconds)
        return LogEvent(job_id=job_id, state=PipelineState.BENCHMARKING, level="INFO", data=data,
                        message=f"Actual GPU extension wall latency: {iterations} iterations after {warmup} warmups; "
                                f"shape={shape}, dtype=float32; synchronized boundaries; {hardware}. "
                                "CPU speedup was not measured.")


def main(arguments: list[str]) -> int:
    if len(arguments) != 2 or Path(arguments[1]) != Path("/workspace/benchmark_report.json"):
        raise ValueError("Usage: benchmark.py JOB_ID /workspace/benchmark_report.json")
    event = benchmark(arguments[0])
    with Path(arguments[1]).open("x", encoding="utf-8") as output:
        output.write(event.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
