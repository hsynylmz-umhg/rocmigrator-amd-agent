"""
tests/test_pipeline.py — ROCmigrator Unit and Integration Tests.
Pydantic v2 contracts, fingerprint DB, patch policy, rollback, and state machine verification.
"""

import os
import unittest
from pydantic import ValidationError

from contracts.state_schemas import PipelineState
from contracts.patch_schemas import PatchProposal
from contracts.verification_schemas import NumericalResult, VerificationReport
from agent_orchestrator.fingerprints.db import FingerprintDB
from agent_orchestrator.policies.patch_policy import PatchPolicy
from agent_orchestrator.rollback import RollbackManager


class TestContracts(unittest.TestCase):
    def test_patch_proposal_line_budget_violation(self):
        """ValidationError must be raised when a single patch > 120 lines."""
        with self.assertRaises(ValidationError):
            PatchProposal(
                patch_id="p1",
                file_path="csrc/elementwise.cu",
                diff="dummy",
                lines_added=121,
                lines_deleted=0,
                explanation="Exceeds budget",
                modifies_dependencies=False,
                modifies_public_api=False,
                modifies_tests_or_tolerances=False,
            )

    def test_patch_proposal_forbidden_flags(self):
        """Must raise an error when forbidden flags (dependency, api, test) are True."""
        with self.assertRaises(ValidationError):
            PatchProposal(
                patch_id="p2",
                file_path="csrc/elementwise.cu",
                diff="dummy",
                lines_added=10,
                lines_deleted=0,
                explanation="Modifies deps",
                modifies_dependencies=True,
            )

        with self.assertRaises(ValidationError):
            PatchProposal(
                patch_id="p3",
                file_path="csrc/elementwise.cu",
                diff="dummy",
                lines_added=10,
                lines_deleted=0,
                explanation="Modifies API",
                modifies_public_api=True,
            )

        with self.assertRaises(ValidationError):
            PatchProposal(
                patch_id="p4",
                file_path="csrc/elementwise.cu",
                diff="dummy",
                lines_added=10,
                lines_deleted=0,
                explanation="Modifies tests",
                modifies_tests_or_tolerances=True,
            )

    def test_verification_report_valid(self):
        """VerificationReport Pydantic v2 model must validate successfully."""
        num_res = NumericalResult(
            seed=42,
            shape=[128, 64],
            dtype="float32",
            atol=1e-5,
            rtol=1e-5,
            max_abs_err=0.0,
            max_rel_err=0.0,
            mismatch_ratio=0.0,
            nan_inf_detected=False,
            passed=True,
        )
        report = VerificationReport(
            job_id="test-job",
            overall_status="VERIFIED",
            cpu_reference_verified=True,
            determinism_passed=True,
            results=[num_res],
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
            summary="All tests passed",
        )
        self.assertEqual(report.overall_status, "VERIFIED")
        self.assertTrue(report.cpu_reference_verified)


class TestFingerprints(unittest.TestCase):
    def test_fingerprint_classification_and_max_repetition(self):
        db = FingerprintDB()
        sample_log = "error: use of undeclared identifier '__CUDA_ARCH__'"
        fps = db.classify(sample_log)
        self.assertTrue(len(fps) > 0)
        self.assertEqual(fps[0].id, "FP_CUDA_ARCH")

        # 1st occurrence: Allowed
        self.assertTrue(db.record_occurrence("FP_CUDA_ARCH"))
        # 2nd occurrence: Allowed
        self.assertTrue(db.record_occurrence("FP_CUDA_ARCH"))
        # 3rd occurrence: REJECTED (max 2 rule)
        self.assertFalse(db.record_occurrence("FP_CUDA_ARCH"))


class TestPatchPolicy(unittest.TestCase):
    def test_patch_policy_validation(self):
        policy = PatchPolicy(total_cuda_loc=1000)
        valid_proposal = PatchProposal(
            patch_id="p_ok",
            file_path="csrc/elementwise.cu",
            diff="--- a/csrc/elementwise.cu\n+++ b/csrc/elementwise.cu\n@@ -1 +1 @@\n- foo\n+ bar",
            lines_added=10,
            lines_deleted=5,
            explanation="Valid patch",
            allowlisted=True,
            modifies_dependencies=False,
            modifies_public_api=False,
            modifies_tests_or_tolerances=False,
        )
        res = policy.validate(valid_proposal)
        self.assertTrue(res.valid)

        # File not in allowlist
        invalid_file_proposal = PatchProposal(
            patch_id="p_bad_file",
            file_path="secret_exploit.sh",
            diff="dummy",
            lines_added=5,
            lines_deleted=0,
            explanation="Disallowed file",
            allowlisted=False,
            modifies_dependencies=False,
            modifies_public_api=False,
            modifies_tests_or_tolerances=False,
        )
        res2 = policy.validate(invalid_file_proposal)
        self.assertFalse(res2.valid)


class TestRollback(unittest.TestCase):
    def test_rollback_consecutive_stalls(self):
        rb = RollbackManager(repo_path=".")
        rb.record_commit("commit1", is_progress=True)
        self.assertFalse(rb.should_rollback())

        rb.record_commit("commit2", is_progress=False)
        self.assertFalse(rb.should_rollback())

        # 2nd consecutive stall without progress
        rb.record_commit("commit3", is_progress=False)
        self.assertTrue(rb.should_rollback())


if __name__ == "__main__":
    unittest.main()
