"""
fixtures/golden-repo-03/reference.py — CPU Multi-Kernel Reference Implementation.
"""

try:
    import torch
except ImportError:
    from agent_orchestrator.torch_compat import torch


def relu_cpu(x: torch.Tensor) -> torch.Tensor:
    return torch.where(x > 0, x, x * 0.0)


def scale_cpu(x: torch.Tensor, scale: float) -> torch.Tensor:
    return x * scale
