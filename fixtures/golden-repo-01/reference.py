"""
fixtures/golden-repo-01/reference.py — CPU / PyTorch Reference Implementation.
Used as ground truth during BASELINE and VERIFYING stages.
"""

try:
    import torch
except ImportError:
    from agent_orchestrator.torch_compat import torch


def fused_bias_leaky_relu_cpu(x: torch.Tensor, bias: torch.Tensor, alpha: float = 0.01) -> torch.Tensor:
    """
    CPU / PyTorch reference verification.
    x: [..., C] tensor
    bias: [C] or broadcastable tensor
    alpha: LeakyReLU negative slope
    """
    val = x + bias
    return torch.where(val > 0, val, val * alpha)
