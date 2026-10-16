"""Strict API and SSE contracts with closed, immutable event payloads."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.patch_schemas import PatchProposal
from contracts.state_schemas import NonblankText, PipelineState
from contracts.verification_schemas import VerificationReport


class EmptyLogData(BaseModel):
    """Represent an event without structured data; unknown keys are rejected."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )


class AnalysisLogData(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    cu_files: tuple[NonblankText, ...] = Field(
        ..., min_length=1, max_length=5,
        description=(
            "List the 1–5 CUDA source/header paths actually found by analysis. Preserve "
            "their exact spelling; do not invent files. JSON arrays and Python lists "
            "are copied into an immutable tuple with strictly validated strings."
        ),
        examples=[["csrc/elementwise.cu"]],
    )
    total_loc: int = Field(
        ..., ge=0, le=2000,
        description=(
            "Report the integer CUDA line count measured by analysis, from 0 through "
            "2000. Do not estimate the count or omit lines to satisfy the scope limit."
        ),
        examples=[150],
    )
    setup_path: NonblankText = Field(
        ...,
        description=(
            "Copy the setup.py path located by analysis. Do not invent a build file "
            "or substitute a path that was not inspected."
        ),
        examples=["setup.py"],
    )

    @field_validator("cu_files", mode="before")
    @classmethod
    def freeze_file_list(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class BenchmarkLogData(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    avg_latency_ms: float = Field(
        ..., ge=0.0, allow_inf_nan=False,
        description=(
            "Report the measured mean latency in milliseconds as a finite, nonnegative "
            "number. Do not fabricate timing data or silently substitute different units."
        ),
        examples=[1.25],
    )
    throughput_elements_per_sec: float = Field(
        ..., ge=0.0, allow_inf_nan=False,
        description=(
            "Report measured throughput in elements per second as a finite, nonnegative "
            "number. Do not infer performance from compilation success or invent a result."
        ),
        examples=[838860.8],
    )


class PRLogData(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    title: NonblankText = Field(
        ...,
        description=(
            "Copy the pull request title returned by the handler. Do not introduce "
            "claims about repairs or checks that were not performed."
        ),
        examples=["feat(rocm): Port PyTorch CUDAExtension to ROCm/HIP"],
    )
    body: NonblankText = Field(
        ...,
        description=(
            "Copy the handler's pull request description, preserving actual verification "
            "results. Do not fabricate checks, approvals, or benchmark claims."
        ),
        examples=["HIP port verified against the CPU reference; user approval recorded."],
    )
    branch: NonblankText = Field(
        ...,
        description=(
            "Copy the pull request branch selected by the job handler. Do not invent "
            "a branch or silently change the job's configured destination."
        ),
        examples=["hip-port"],
    )


class LogEvent(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    job_id: NonblankText = Field(
        ...,
        description=(
            "Copy the exact job identifier from the emitting engine. Do not attribute "
            "another job's log message or payload to this event."
        ),
        examples=["job-001"],
    )
    timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description=(
            "Record the timezone-aware emission time; omit it to use current UTC time. "
            "In JSON supply ISO 8601 with an offset; do not invent an event time."
        ),
        examples=["2026-09-21T12:00:00Z"],
    )
    level: Literal["INFO", "WARNING", "ERROR", "STEP"] = Field(
        "INFO",
        description=(
            "Select exactly INFO, WARNING, ERROR, or STEP according to the observed "
            "event. Do not invent a level or downgrade a failure to hide it."
        ),
        examples=["INFO", "ERROR"],
    )
    state: PipelineState = Field(
        ...,
        description=(
            "Copy the engine's actual PipelineState when the event was emitted. "
            "Do not replace it with a future state or infer completion from a log message."
        ),
        examples=["ANALYSIS"],
    )
    message: NonblankText = Field(
        ...,
        description=(
            "Report the observed event or failure using nonblank text. Include only "
            "facts provided by the engine; never fabricate execution or verification results."
        ),
        examples=["Analysis successful: 1 CUDA file, 150 total LOC."],
    )
    data: EmptyLogData | AnalysisLogData | PatchProposal | BenchmarkLogData | PRLogData | None = Field(
        default_factory=EmptyLogData,
        description=(
            "Provide exactly one complete known payload: analysis, patch proposal, "
            "benchmark, or pull request data. Use {} or null when absent; preserve "
            "the existing flat keys and do not mix payloads or add arbitrary fields."
        ),
        examples=[{}, {"cu_files": ["csrc/elementwise.cu"], "total_loc": 150, "setup_path": "setup.py"}],
    )


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    repo_path: NonblankText = Field(
        ...,
        description=(
            "Provide the user's exact target repository path as nonblank text. Do not "
            "invent a repository, expand the path into a command, or claim it was inspected."
        ),
        examples=["fixtures/golden-repo-01"],
    )
    target_branch: NonblankText = Field(
        "hip-port",
        description=(
            "Use the requested HIP port branch name, or retain hip-port when unspecified. "
            "Treat it as a branch identifier and never as executable command text."
        ),
        examples=["hip-port"],
    )
    max_repair_rounds: int = Field(
        6, ge=1, le=6,
        description=(
            "Set an integer repair-round limit from 1 through 6; omit it to use 6. "
            "Never exceed the hard cap or encode the limit as a string or boolean."
        ),
        examples=[6, 3],
    )


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    job_id: NonblankText = Field(
        ...,
        description=(
            "Copy the exact identifier of the job being queried. Do not create a "
            "new identifier or attach another job's state or report."
        ),
        examples=["job-001"],
    )
    current_state: PipelineState = Field(
        ...,
        description=(
            "Report the engine's current PipelineState exactly. Do not advance it "
            "based on a requested transition or assume that approval was granted."
        ),
        examples=["CREATED"],
    )
    repair_rounds_used: int = Field(
        0, ge=0, le=6,
        description=(
            "Report the actual integer number of repair rounds used, from 0 through 6. "
            "Do not reset this count between retries or report rounds that did not execute."
        ),
        examples=[0, 2],
    )
    best_known_commit: NonblankText | None = Field(
        None,
        description=(
            "Copy the rollback manager's recorded best-known commit identifier. Use "
            "null when none is recorded; do not guess a revision or fabricate a hash."
        ),
        examples=["0123456789abcdef0123456789abcdef01234567", None],
    )
    verification_report: VerificationReport | None = Field(
        None,
        description=(
            "Include the validated verification report for this same job when available. "
            "Use null before verification; never substitute another job's results."
        ),
        examples=[None],
    )

    @model_validator(mode="after")
    def validate_report_job(self) -> "JobStatusResponse":
        if self.verification_report is not None and self.verification_report.job_id != self.job_id:
            raise ValueError("Verification report must belong to the requested job.")
        return self


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    job_id: NonblankText = Field(
        ...,
        description=(
            "Copy the identifier of the job presented to the user for approval. "
            "Do not transfer an approval decision from another job."
        ),
        examples=["job-001"],
    )
    approved: bool = Field(
        ...,
        description=(
            "Record the user's explicit decision as a boolean: true for approval and "
            "false for rejection. Never infer consent from silence or a successful report."
        ),
        examples=[True, False],
    )
    comments: str | None = Field(
        None,
        description=(
            "Preserve the user's comments verbatim when supplied. Use null when absent; "
            "do not invent feedback or reinterpret comments as an approval decision."
        ),
        examples=["Approved after reviewing the verification report.", None],
    )


class PRPayload(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    job_id: NonblankText = Field(
        ...,
        description=(
            "Copy the identifier of the verified job approved for pull request creation. "
            "Do not reuse an approval or report belonging to another job."
        ),
        examples=["job-001"],
    )
    approved_by_user: bool = Field(
        ...,
        description=(
            "Set true only after explicit USER_APPROVAL was recorded for this job. "
            "False is rejected; the engine must still verify approval provenance and "
            "passing verification before creating a pull request."
        ),
        examples=[True],
    )
    report_url: NonblankText | None = Field(
        None,
        description=(
            "Copy the actual published verification-report URL when available. Use "
            "null when no URL exists; never fabricate a link or evidence of verification."
        ),
        examples=["https://example.com/reports/job-001", None],
    )
    pr_title: NonblankText = Field(
        ...,
        description=(
            "Provide a nonblank title describing the verified repair. Do not claim "
            "support for features, hardware, or repositories that were not checked."
        ),
        examples=["feat(rocm): Port elementwise extension to HIP"],
    )
    pr_body: NonblankText = Field(
        ...,
        description=(
            "Describe the actual patch and recorded verification results. Do not "
            "fabricate benchmarks, approvals, test runs, or changes outside the repair scope."
        ),
        examples=["Replaced the CUDA runtime include; CPU-reference verification passed."],
    )

    @field_validator("approved_by_user")
    @classmethod
    def require_user_approval(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Pull request payload requires explicit user approval.")
        return value
