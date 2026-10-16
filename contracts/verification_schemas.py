"""Strict, immutable contracts for numerical verification evidence and reports."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class NumericalResult(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True, revalidate_instances="always"
    )

    seed: int = Field(
        ...,
        description="Copy the exact integer random seed used for this executed test; do not invent a seed or encode it as a string.",
        examples=[42],
    )
    shape: tuple[Annotated[int, Field(ge=0)], ...] = Field(
        ...,
        description="Copy the tested input dimensions in order as nonnegative integers; use an empty array only for a scalar tensor. Do not infer dimensions from another test.",
        examples=[[128, 64], []],
    )
    dtype: str = Field(
        ...,
        min_length=1,
        pattern=r"\S",
        description="Copy the nonblank dtype label recorded by the runner, including any library qualification. Do not substitute an untested precision.",
        examples=["float32", "torch.float64", "<class 'numpy.float32'>"],
    )
    atol: float = Field(
        ...,
        ge=0.0,
        allow_inf_nan=False,
        description="Copy the existing finite, nonnegative absolute tolerance used by the test. Never increase, replace, or fabricate a tolerance to obtain a passing result.",
        examples=[0.00001],
    )
    rtol: float = Field(
        ...,
        ge=0.0,
        allow_inf_nan=False,
        description="Copy the existing finite, nonnegative relative tolerance used by the test. Never increase, replace, or fabricate a tolerance to obtain a passing result.",
        examples=[0.00001],
    )
    max_abs_err: float = Field(
        ...,
        ge=0.0,
        allow_inf_nan=False,
        description="Record the measured finite, nonnegative maximum absolute error against the CPU reference. Do not replace an unmeasured or nonfinite error with zero.",
        examples=[0.0, 0.000002],
    )
    max_rel_err: float = Field(
        ...,
        ge=0.0,
        allow_inf_nan=False,
        description="Record the measured finite, nonnegative maximum relative error using the runner's definition. Do not infer it from maximum absolute error or fabricate zero.",
        examples=[0.0, 0.000003],
    )
    mismatch_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
        description="Record the measured fraction of elements outside the test's combined absolute and relative tolerance, between 0 and 1 inclusive. A passing test must have zero mismatches.",
        examples=[0.0, 0.25],
    )
    nan_inf_detected: bool = Field(
        ...,
        description="Set true exactly when the executed NaN/Inf checks detect a nonfinite value. Never hide nonfinite values or substitute false for a check that did not run.",
        examples=[False, True],
    )
    passed: bool = Field(
        ...,
        description="Copy the executed comparison outcome; true requires a passing CPU-reference comparison with no mismatches or NaN/Inf. Never infer success solely from aggregate error maxima.",
        examples=[True, False],
    )

    @field_validator("shape", mode="before")
    @classmethod
    def freeze_shape(cls, value: object) -> object:
        # Existing runners supply lists; copy the container without coercing its items.
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_pass_evidence(self) -> "NumericalResult":
        if self.passed and (self.nan_inf_detected or self.mismatch_ratio != 0.0):
            raise ValueError("A passing numerical result cannot contain NaN/Inf or mismatches.")
        return self


class VerificationReport(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", validate_default=True, revalidate_instances="always"
    )

    job_id: str = Field(
        ...,
        min_length=1,
        pattern=r"\S",
        description="Copy the nonblank identifier of the job that produced this report. Never generate a replacement identifier or attach another job's results.",
        examples=["job-001"],
    )
    overall_status: Literal["VERIFIED", "FAILED", "ROLLED_BACK"] = Field(
        ...,
        description="Use exactly VERIFIED, FAILED, or ROLLED_BACK according to the observed outcome. VERIFIED requires CPU-reference verification, determinism, and nonempty passing results with no failures.",
        examples=["VERIFIED", "FAILED", "ROLLED_BACK"],
    )
    cpu_reference_verified: bool = Field(
        ...,
        description="Set true only after comparing the migrated kernel against the independent CPU reference. An unavailable reference, skipped check, or CPU fallback cannot establish verification.",
        examples=[True, False],
    )
    determinism_passed: bool = Field(
        ...,
        description="Set true only after repeated executions with identical inputs and seeds pass the determinism test. A single execution or skipped test provides no such evidence.",
        examples=[True, False],
    )
    results: tuple[NumericalResult, ...] = Field(
        default_factory=tuple,
        description="Include one complete NumericalResult for every executed case in its recorded order. Do not omit failures, fabricate cases, or use an empty array for a VERIFIED report.",
        examples=[[
            {
                "seed": 42,
                "shape": [128, 64],
                "dtype": "float32",
                "atol": 0.00001,
                "rtol": 0.00001,
                "max_abs_err": 0.0,
                "max_rel_err": 0.0,
                "mismatch_ratio": 0.0,
                "nan_inf_detected": False,
                "passed": True,
            }
        ]],
    )
    total_tests: int = Field(
        0,
        ge=0,
        description="Set this nonnegative integer to exactly the number of entries in results. Do not count planned, skipped, or fabricated tests.",
        examples=[1, 18],
    )
    passed_tests: int = Field(
        0,
        ge=0,
        description="Set this nonnegative integer to exactly the number of results whose passed field is true. Do not count a failed or unexecuted test as passing.",
        examples=[1, 18],
    )
    failed_tests: int = Field(
        0,
        ge=0,
        description="Set this nonnegative integer to exactly the number of results whose passed field is false. Preserve every failure and ensure passed_tests plus failed_tests equals total_tests.",
        examples=[0, 1],
    )
    summary: str = Field(
        ...,
        min_length=1,
        pattern=r"\S",
        description="Describe only the recorded outcome, failures, and limitations in nonblank English text. Do not claim GPU execution, CPU-reference coverage, or successful checks without supporting evidence.",
        examples=["18 tests completed. Determinism: Passed."],
    )
    timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record the timezone-aware creation time; omit this field to use current UTC time. In JSON, supply the actual ISO 8601 timestamp with an explicit offset.",
        examples=["2026-09-21T12:00:00Z"],
    )

    @field_validator("results", mode="before")
    @classmethod
    def freeze_results(cls, value: object) -> object:
        # Preserve list input and JSON arrays while storing immutable evidence.
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_report_evidence(self) -> "VerificationReport":
        actual_passed = sum(result.passed for result in self.results)
        if (
            self.total_tests != len(self.results)
            or self.passed_tests != actual_passed
            or self.failed_tests != len(self.results) - actual_passed
        ):
            raise ValueError("Verification counts must exactly match the recorded results.")
        if self.overall_status == "VERIFIED" and (
            not self.cpu_reference_verified
            or not self.determinism_passed
            or not self.results
            or self.failed_tests != 0
        ):
            raise ValueError(
                "VERIFIED requires CPU-reference verification, determinism, and nonempty passing results."
            )
        return self
