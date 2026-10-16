"""
contracts/state_schemas.py — Pipeline State Machine Contracts.
Type-safe state transitions and validation using Pydantic v2.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


NonblankText = Annotated[str, Field(min_length=1, pattern=r"\S")]


class PipelineState(str, Enum):
    CREATED = "CREATED"
    CLONING = "CLONING"
    SECURITY_SCAN = "SECURITY_SCAN"
    ANALYSIS = "ANALYSIS"
    BASELINE = "BASELINE"
    HIPIFICATION = "HIPIFICATION"
    COMPILING = "COMPILING"
    REPAIR = "REPAIR"
    VERIFYING = "VERIFYING"
    BENCHMARKING = "BENCHMARKING"
    REPORT = "REPORT"
    USER_APPROVAL = "USER_APPROVAL"
    PR_CREATED = "PR_CREATED"
    ROLLED_BACK = "ROLLED_BACK"


class TransitionMetadata(BaseModel):
    """Only the metadata keys consumed by the existing handlers are allowed."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    job_id: NonblankText | None = Field(
        None,
        description=(
            "Copy the existing job identifier when passing it to a state handler. "
            "Omit it or use null when unnecessary; never invent a second job identity."
        ),
        examples=["job-001", None],
    )
    target_branch: NonblankText | None = Field(
        None,
        description=(
            "Copy the target branch from the approved job configuration when needed by "
            "the handler. Omit it or use null when unnecessary; do not invent a branch."
        ),
        examples=["hip-port", None],
    )


class StateTransitionRequest(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    job_id: NonblankText = Field(
        ...,
        description=(
            "Copy the exact identifier of the existing job whose transition is requested. "
            "Do not generate a replacement identifier or use a blank value."
        ),
        examples=["job-001"],
    )
    target_state: PipelineState = Field(
        ...,
        description=(
            "Choose an exact PipelineState value for the requested next state. The engine "
            "must authorize the transition from its actual current state; this request "
            "does not prove that prerequisites or user approval have been satisfied."
        ),
        examples=["COMPILING"],
    )
    metadata: TransitionMetadata = Field(
        default_factory=TransitionMetadata,
        description=(
            "Provide only the declared job_id and target_branch handler context when "
            "available. Use an empty object when none is needed; do not add arbitrary "
            "keys, execution commands, credentials, or invented context."
        ),
        examples=[{}, {"job_id": "job-001", "target_branch": "hip-port"}],
    )

    @model_validator(mode="after")
    def validate_job_identity(self) -> "StateTransitionRequest":
        if self.metadata.job_id is not None and self.metadata.job_id != self.job_id:
            raise ValueError("Transition metadata must refer to the requested job.")
        return self


class StateTransitionEvent(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    job_id: NonblankText = Field(
        ...,
        description=(
            "Copy the exact job identifier from the engine that emitted this event. "
            "Do not associate a transition with another job or invent an identifier."
        ),
        examples=["job-001"],
    )
    from_state: PipelineState = Field(
        ...,
        description=(
            "Record the engine's actual state before the transition attempt using an "
            "exact PipelineState value. Do not infer it from a requested target state."
        ),
        examples=["COMPILING"],
    )
    to_state: PipelineState = Field(
        ...,
        description=(
            "Record the attempted destination using an exact PipelineState value. "
            "Read success to determine whether the transition actually completed."
        ),
        examples=["REPAIR"],
    )
    timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description=(
            "Record the timezone-aware event time; omit it to use the current UTC time. "
            "In JSON use an ISO 8601 timestamp with an offset; do not invent an event time."
        ),
        examples=["2026-09-21T12:00:00Z"],
    )
    success: bool = Field(
        True,
        description=(
            "Report the engine's actual transition outcome as a boolean. Set false for "
            "a rejected or failed transition; never infer success from the request alone."
        ),
        examples=[True, False],
    )
    message: NonblankText | None = Field(
        None,
        description=(
            "Copy the observed transition explanation or error, without inventing results. "
            "Use null when no message was recorded."
        ),
        examples=["Compilation failed; entering repair.", None],
    )
    commit_hash: NonblankText | None = Field(
        None,
        description=(
            "Copy the commit identifier recorded for this transition from Git or the "
            "engine. Use null when no commit was recorded; never fabricate a hash."
        ),
        examples=["0123456789abcdef0123456789abcdef01234567", None],
    )
