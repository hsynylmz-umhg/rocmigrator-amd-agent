"""
contracts/patch_schemas.py — Bounded LLM Patch Contracts.
Strict patch schemas conforming to rules via Pydantic v2.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class PatchProposal(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    patch_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Provide the nonblank identifier assigned to this proposal. Keep it identical in "
            "its validation result; do not substitute another proposal's identifier."
        ),
        examples=["patch_round_1_FP_CUDA_HEADER"],
    )
    file_path: str = Field(
        ...,
        min_length=1,
        description=(
            "Copy the target repository-relative path from the supplied repair context. "
            "Target only a file permitted by the orchestrator's allowlist; do not invent "
            "a path or treat this declaration as proof that the file is allowed."
        ),
        examples=["csrc/elementwise.cu"],
    )
    diff: str = Field(
        ...,
        min_length=1,
        description=(
            "Provide a nonblank unified diff for the supplied target file and error context. "
            "Include only the bounded repair, with no Markdown fences or commentary. "
            "Preserve kernels, dependencies, public APIs, tests, and tolerances; the "
            "orchestrator must independently check applicability and policy before applying it."
        ),
        examples=[
            "--- a/csrc/elementwise.cu\n+++ b/csrc/elementwise.cu\n"
            "@@ -1 +1 @@\n-#include <cuda_runtime.h>\n+#include <hip/hip_runtime.h>\n"
        ],
    )
    fingerprint_id: Optional[str] = Field(
        None,
        min_length=1,
        description=(
            "Copy the associated compiler-error fingerprint identifier from the supplied "
            "context. Use null when none is associated; never invent a fingerprint or use "
            "an empty string as a replacement for null."
        ),
        examples=["FP_CUDA_HEADER", None],
    )
    lines_added: int = Field(
        ...,
        ge=0,
        le=120,
        description=(
            "Provide the exact integer count of added content lines in the diff, excluding "
            "diff headers and context. Do not estimate or underreport it; added plus deleted "
            "lines must not exceed the single-patch limit of 120."
        ),
        examples=[1],
    )
    lines_deleted: int = Field(
        ...,
        ge=0,
        le=120,
        description=(
            "Provide the exact integer count of deleted content lines in the diff, excluding "
            "diff headers and context. Count replacements as both a deletion and an addition; "
            "deleted plus added lines must not exceed 120."
        ),
        examples=[1],
    )
    explanation: str = Field(
        ...,
        min_length=1,
        description=(
            "Explain how the proposed changes address the supplied compiler error while "
            "preserving kernel behavior. Refer only to evidence in the provided context; "
            "do not claim compilation, numerical verification, or benchmarks have passed."
        ),
        examples=["Replace the CUDA runtime include with the HIP runtime include for FP_CUDA_HEADER."],
    )
    allowlisted: bool = Field(
        True,
        description=(
            "Record the actual allowlist assessment as a boolean; use false for a target "
            "that is not authorized. Do not treat true as permission to apply the patch: "
            "the orchestrator must independently check the target against its allowlist."
        ),
        examples=[True, False],
    )
    modifies_dependencies: bool = Field(
        False,
        description=(
            "Keep false: adding, removing, or changing dependencies is forbidden. If the "
            "repair requires a dependency change, do not submit it as an admissible proposal."
        ),
        examples=[False],
    )
    modifies_public_api: bool = Field(
        False,
        description=(
            "Keep false: changing public API names, signatures, or behavior is forbidden. "
            "Do not hide an API change by declaring this flag false."
        ),
        examples=[False],
    )
    modifies_tests_or_tolerances: bool = Field(
        False,
        description=(
            "Keep false: modifying tests, reference expectations, or numerical tolerances "
            "is forbidden. Never weaken verification to make the proposed repair pass."
        ),
        examples=[False],
    )

    @field_validator("patch_id", "file_path", "diff", "fingerprint_id", "explanation")
    @classmethod
    def validate_nonblank_text(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(f"{info.field_name} cannot be blank.")
        return v

    @model_validator(mode="after")
    def validate_lines_budget(self) -> "PatchProposal":
        patch_lines = self.lines_added + self.lines_deleted
        if patch_lines > 120:
            raise ValueError(f"Single patch budget exceeded: {patch_lines} changed lines (maximum 120).")
        return self

    @field_validator("modifies_dependencies", "modifies_public_api", "modifies_tests_or_tolerances")
    @classmethod
    def validate_forbidden_changes(cls, v: bool, info: ValidationInfo) -> bool:
        if v:
            raise ValueError(f"{info.field_name} is strictly forbidden (cannot be True).")
        return v


class PatchValidationResult(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True,
        revalidate_instances="always",
    )

    patch_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Copy the exact nonblank patch_id of the proposal that was checked. Do not "
            "generate a new identifier or attach another proposal's validation outcome."
        ),
        examples=["patch_round_1_FP_CUDA_HEADER"],
    )
    valid: bool = Field(
        ...,
        description=(
            "Report the deterministic validator's actual decision as a boolean. Set true "
            "only when all required patch checks pass; do not infer validity from the "
            "proposal's explanation or self-declared safety flags."
        ),
        examples=[True, False],
    )
    error_message: Optional[str] = Field(
        None,
        min_length=1,
        description=(
            "Copy the observed validation failure explanation when available. Use null "
            "when there is no error message; do not invent a failure or conceal one."
        ),
        examples=[None, "Single patch budget exceeded: 121 > 120"],
    )
    git_apply_check: bool = Field(
        False,
        description=(
            "Set true only when git apply --check actually succeeded for this exact diff "
            "and repository state. Keep false when the check failed or was not run; "
            "never substitute an LLM prediction for the command result."
        ),
        examples=[False, True],
    )
    budget_remaining: int = Field(
        300,
        ge=0,
        le=300,
        description=(
            "Report the orchestrator's remaining cumulative changed-line allowance as an "
            "integer from 0 through 300. Use the applicable CUDA-LOC limit and recorded "
            "budget usage; do not reset the allowance between repair rounds or invent capacity."
        ),
        examples=[298, 0],
    )

    @field_validator("patch_id", "error_message")
    @classmethod
    def validate_nonblank_text(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(f"{info.field_name} cannot be blank.")
        return v
