"""
contracts package — Pydantic v2 schemas and contracts.
"""

from contracts.state_schemas import PipelineState, StateTransitionRequest, StateTransitionEvent
from contracts.patch_schemas import PatchProposal, PatchValidationResult
from contracts.verification_schemas import NumericalResult, VerificationReport
from contracts.api_schemas import LogEvent, JobCreateRequest, JobStatusResponse, ApprovalRequest, PRPayload

__all__ = [
    "PipelineState",
    "StateTransitionRequest",
    "StateTransitionEvent",
    "PatchProposal",
    "PatchValidationResult",
    "NumericalResult",
    "VerificationReport",
    "LogEvent",
    "JobCreateRequest",
    "JobStatusResponse",
    "ApprovalRequest",
    "PRPayload",
]
