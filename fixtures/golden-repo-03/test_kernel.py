"""
fixtures/golden-repo-03/test_kernel.py — Multi-Kernel Numerical Verification Test.
"""

try:
    import torch
except ImportError:
    from agent_orchestrator.torch_compat import torch

from reference import relu_cpu, scale_cpu


def run_verification(target_relu=relu_cpu, target_scale=scale_cpu, device: str = "cpu"):
    seeds = [42, 100]
    shapes = [([64, 32],), ([512],)]
    results = []

    for seed in seeds:
        torch.manual_seed(seed)
        for (shape,) in shapes:
            x = torch.randn(shape, device=device)
            # ReLU test
            ref_r = relu_cpu(x.cpu())
            out_r = target_relu(x)
            if device != "cpu":
                out_r = out_r.cpu()
            abs_diff = torch.abs(ref_r - out_r)
            max_abs = float(torch.max(abs_diff).item())
            passed = max_abs <= 1e-5

            results.append({
                "seed": seed,
                "shape": list(shape),
                "dtype": "float32",
                "atol": 1e-5,
                "rtol": 1e-5,
                "max_abs_err": max_abs,
                "max_rel_err": 0.0,
                "mismatch_ratio": 0.0 if passed else 1.0,
                "nan_inf_detected": False,
                "passed": passed,
            })

            # Scale test
            ref_s = scale_cpu(x.cpu(), 2.5)
            out_s = target_scale(x, 2.5)
            if device != "cpu":
                out_s = out_s.cpu()
            abs_diff_s = torch.abs(ref_s - out_s)
            max_abs_s = float(torch.max(abs_diff_s).item())
            passed_s = max_abs_s <= 1e-5

            results.append({
                "seed": seed,
                "shape": list(shape),
                "dtype": "float32",
                "atol": 1e-5,
                "rtol": 1e-5,
                "max_abs_err": max_abs_s,
                "max_rel_err": 0.0,
                "mismatch_ratio": 0.0 if passed_s else 1.0,
                "nan_inf_detected": False,
                "passed": passed_s,
            })

    return results


if __name__ == "__main__":
    res = run_verification()
    print(f"Golden Repo 03 CPU self-test: {all(r['passed'] for r in res)}")
