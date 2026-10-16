"""
fixtures/golden-repo-01/test_kernel.py — Numerical Verification Test.
torch.testing.assert_close, multi-seed, shape, and dtype verification.
"""

try:
    import torch
except ImportError:
    from agent_orchestrator.torch_compat import torch

from reference import fused_bias_leaky_relu_cpu


def run_verification(target_fn, device: str = "cpu"):
    """
    target_fn: Function to verify (fused_bias_leaky_relu)
    device: 'cpu' or 'cuda'/'hip'
    """
    seeds = [42, 1337, 2026]
    shapes = [
        ([128, 64], [64]),
        ([32, 128, 256], [256]),
        ([1024], [1024]),
    ]
    dtypes = [torch.float32, torch.float64]
    alpha = 0.01

    results = []

    for seed in seeds:
        torch.manual_seed(seed)
        for x_shape, b_shape in shapes:
            for dtype in dtypes:
                x = torch.randn(x_shape, dtype=dtype, device=device)
                bias = torch.randn(b_shape, dtype=dtype, device=device)

                # CPU Baseline Reference
                ref_out = fused_bias_leaky_relu_cpu(x.cpu(), bias.cpu(), alpha=alpha)

                # Target Output
                target_out = target_fn(x, bias, alpha=alpha)
                if device != "cpu":
                    target_out = target_out.cpu()

                # Numerical verification
                atol = 1e-5 if dtype == torch.float32 else 1e-7
                rtol = 1e-5 if dtype == torch.float32 else 1e-7

                abs_diff = torch.abs(ref_out - target_out)
                max_abs_err = float(torch.max(abs_diff).item())
                rel_diff = abs_diff / (torch.abs(ref_out) + 1e-12)
                max_rel_err = float(torch.max(rel_diff).item())

                mismatches = (abs_diff > (atol + rtol * torch.abs(ref_out))).sum().item()
                mismatch_ratio = float(mismatches) / float(ref_out.numel())

                nan_inf = bool(torch.isnan(target_out).any().item() or torch.isinf(target_out).any().item())

                passed = (max_abs_err <= atol or max_rel_err <= rtol) and not nan_inf

                results.append({
                    "seed": seed,
                    "shape": x_shape,
                    "dtype": str(dtype),
                    "atol": atol,
                    "rtol": rtol,
                    "max_abs_err": max_abs_err,
                    "max_rel_err": max_rel_err,
                    "mismatch_ratio": mismatch_ratio,
                    "nan_inf_detected": nan_inf,
                    "passed": passed,
                })

    return results


if __name__ == "__main__":
    # Test with reference itself on CPU
    res = run_verification(fused_bias_leaky_relu_cpu, device="cpu")
    all_passed = all(r["passed"] for r in res)
    print(f"Self-verification on CPU passed: {all_passed} ({len(res)} tests)")
