"""Execute the trusted independent CPU reference before migration."""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, "/opt/rocmigrator")
from contracts.api_schemas import LogEvent
from contracts.state_schemas import PipelineState

spec = importlib.util.spec_from_file_location("trusted_golden_verification", Path(__file__).with_name("verify.py"))
trusted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trusted)


def baseline(job_id: str) -> LogEvent:
    import torch
    trusted.validate_job_id(job_id)
    cases = 0
    with torch.inference_mode():
        for seed in trusted.SEEDS:
            torch.manual_seed(seed)
            for shape in trusted.SHAPES:
                for dtype in (torch.float32, torch.float64):
                    x = torch.randn(shape, dtype=dtype, device="cpu")
                    bias = torch.randn((shape[-1],), dtype=dtype, device="cpu")
                    result = trusted.cpu_reference(torch, x, bias)
                    if result.device.type != "cpu" or not bool(torch.isfinite(result).all().item()):
                        raise RuntimeError("Trusted CPU reference produced invalid output.")
                    cases += 1
    return LogEvent(job_id=job_id, state=PipelineState.BASELINE, level="INFO", data=None,
                    message=f"Executed trusted independent Golden 01 CPU reference for {cases} cases: "
                            "seeds 42/1337/2026, three shapes, float32/float64; all CPU outputs finite. "
                            "GPU verification has not run at this stage.")


def main(arguments: list[str]) -> int:
    if len(arguments) != 2 or Path(arguments[1]) != Path("/workspace/baseline_report.json"):
        raise ValueError("Usage: baseline.py JOB_ID /workspace/baseline_report.json")
    event = baseline(arguments[0])
    with Path(arguments[1]).open("x", encoding="utf-8") as output:
        output.write(event.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
