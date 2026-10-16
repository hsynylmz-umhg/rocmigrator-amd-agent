"""
fixtures/golden-repo-02/test_kernel.py — Reduction Numerical Verification Test.
"""

try:
    import torch
except ImportError:
    from agent_orchestrator.torch_compat import torch

from reference import sum_reduction_cpu


def run_verification(target_fn, device: str = "cpu"):
    seeds = [42, 999]
    shapes = [([100],), ([1024],), ([64, 64],)]
    dtypes = [torch.float32]

    results = []
    for seed in seeds:
        torch.manual_seed(seed)
        for (shape,) in shapes:
            for dtype in dtypes:
                x = torch.randn(shape, dtype=dtype, device=device)
                ref_out = sum_reduction_cpu(x.cpu())
                target_out = target_fn(x)
                if device != "cpu":
                    target_out = target_out.cpu()

                atol = 1e-4
                rtol = 1e-4
                abs_diff = torch.abs(ref_out - target_out)
                max_abs_err = float(torch.max(abs_diff).item())
                max_rel_err = float((abs_diff / (torch.abs(ref_out) + 1e-12)).max().item() if hasattr(abs_diff / (torch.abs(ref_out) + 1e-12), 'max') else torch.max(abs_diff / (torch.abs(ref_out) + 1e-12)).item())
                nan_inf = bool(torch.isnan(target_out).any().item() or torch.isinf(target_out).any().item())
                passed = (max_abs_err <= atol or max_rel_err <= rtol) and not nan_inf

                results.append({
                    "seed": seed,
                    "shape": list(shape),
                    "dtype": str(dtype),
                    "atol": atol,
                    "rtol": rtol,
                    "max_abs_err": max_abs_err,
                    "max_rel_err": max_rel_err,
                    "mismatch_ratio": 0.0 if passed else 1.0,
                    "nan_inf_detected": nan_inf,
                    "passed": passed,
                })
    return results


if __name__ == "__main__":
    res = run_verification(sum_reduction_cpu, device="cpu")
    print(f"Golden Repo 02 CPU self-test: {all(r['passed'] for r in res)}")
