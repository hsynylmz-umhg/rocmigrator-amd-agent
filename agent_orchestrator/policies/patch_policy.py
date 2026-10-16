"""
agent_orchestrator/policies/patch_policy.py — Patch Validation and Security Policies.
Strict boundary rules:
- Single patch <= 120 lines
- Total changes <= 300 lines or 15% of CUDA LOC
- Allowlist check (.cu, .cuh, setup.py)
- Dependency/API/test/tolerance changes are STRICTLY FORBIDDEN.
"""

from typing import List, Set
from contracts.patch_schemas import PatchProposal, PatchValidationResult


class PatchPolicy:
    ALLOWED_EXTENSIONS: Set[str] = {".cu", ".cuh", ".h", ".cpp", ".py"}
    ALLOWED_FILES: Set[str] = {"setup.py", "csrc/elementwise.cu", "csrc/elementwise.h"}
    MAX_SINGLE_PATCH_LINES: int = 120
    MAX_TOTAL_BUDGET: int = 300

    def __init__(self, total_cuda_loc: int = 500):
        # Total budget: 300 lines or 15% of CUDA LOC (whichever is smaller)
        loc_limit = max(50, int(total_cuda_loc * 0.15))
        self.max_total_budget = min(self.MAX_TOTAL_BUDGET, loc_limit)
        self.used_budget = 0

    def validate(self, patch: PatchProposal) -> PatchValidationResult:
        # 1. Allowlist check
        norm_path = patch.file_path.replace("\\", "/")
        is_allowed = any(norm_path.endswith(f) for f in self.ALLOWED_FILES) or any(norm_path.endswith(ext) for ext in self.ALLOWED_EXTENSIONS)
        if not is_allowed:
            return PatchValidationResult(
                patch_id=patch.patch_id,
                valid=False,
                error_message=f"File is not in the allowlist: {patch.file_path}",
                budget_remaining=self.max_total_budget - self.used_budget,
            )

        # 2. Single patch line budget check (<= 120 lines)
        patch_lines = patch.lines_added + patch.lines_deleted
        if patch_lines > self.MAX_SINGLE_PATCH_LINES:
            return PatchValidationResult(
                patch_id=patch.patch_id,
                valid=False,
                error_message=f"Single patch budget exceeded: {patch_lines} > {self.MAX_SINGLE_PATCH_LINES}",
                budget_remaining=self.max_total_budget - self.used_budget,
            )

        # 3. Total budget check
        if self.used_budget + patch_lines > self.max_total_budget:
            return PatchValidationResult(
                patch_id=patch.patch_id,
                valid=False,
                error_message=f"Total repair budget exceeded: {self.used_budget + patch_lines} > {self.max_total_budget}",
                budget_remaining=self.max_total_budget - self.used_budget,
            )

        # 4. Forbidden changes check
        if patch.modifies_dependencies:
            return PatchValidationResult(
                patch_id=patch.patch_id,
                valid=False,
                error_message="Adding new dependencies is strictly forbidden.",
                budget_remaining=self.max_total_budget - self.used_budget,
            )

        if patch.modifies_public_api:
            return PatchValidationResult(
                patch_id=patch.patch_id,
                valid=False,
                error_message="Modifying public API signatures is strictly forbidden.",
                budget_remaining=self.max_total_budget - self.used_budget,
            )

        if patch.modifies_tests_or_tolerances:
            return PatchValidationResult(
                patch_id=patch.patch_id,
                valid=False,
                error_message="Modifying test files or tolerance thresholds is strictly forbidden.",
                budget_remaining=self.max_total_budget - self.used_budget,
            )

        # Successful budget reservation
        self.used_budget += patch_lines
        return PatchValidationResult(
            patch_id=patch.patch_id,
            valid=True,
            git_apply_check=True,
            budget_remaining=self.max_total_budget - self.used_budget,
        )
