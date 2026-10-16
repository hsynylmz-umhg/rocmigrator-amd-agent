"""
fixtures/golden-repo-02/reference.py — CPU Reduction Reference Implementation.
"""

try:
    import torch
except ImportError:
    from agent_orchestrator.torch_compat import torch


def sum_reduction_cpu(x: torch.Tensor) -> torch.Tensor:
    """CPU sum reduction ground truth."""
    return x.sum()
