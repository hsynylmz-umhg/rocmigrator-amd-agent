"""Source-checked normalization accepts numeric mistakes, never unknown edits."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from agent_orchestrator import engine
from contracts.api_schemas import AnalysisLogData, JobCreateRequest
from contracts.patch_schemas import PatchProposal
from contracts.state_schemas import PipelineState


HEADERS = "--- a/csrc/elementwise.cu\n+++ b/csrc/elementwise.cu\n"
REPLACEMENT = "-    const int threads = 32;\n+    const int threads = warpSize;\n"
WRONG_HUNK_LENGTHS = (
    HEADERS + "@@ -2,7 +2,7 @@\n"
    + " " + engine._SIM_SOURCE[1] + REPLACEMENT
    + "".join(" " + line for line in engine._SIM_SOURCE[3:6])
)


def candidate(diff=engine._SIM_DIFF, **changes):
    values = {
        "patch_id": "source-checked-patch",
        "file_path": engine._SIM_FILE,
        "diff": diff,
        "fingerprint_id": "FP_WARP_SIZE",
        "lines_added": 1,
        "lines_deleted": 1,
        "explanation": "Repair the synthetic launch assumption.",
    }
    return PatchProposal(**{**values, **changes})


class TestSimulationDiff(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        broadcast = patch.object(engine.log_streamer, "broadcast", new_callable=AsyncMock)
        self.broadcast = broadcast.start()
        self.addCleanup(broadcast.stop)
        store = patch.dict(engine._job_statuses, clear=True)
        store.start()
        self.addCleanup(store.stop)
        self.analysis = AnalysisLogData(
            cu_files=(engine._SIM_FILE,), total_loc=len(engine._SIM_SOURCE), setup_path="setup.py",
        )

    async def validate(self, proposal, used_lines=0):
        return await engine._validate_patch(
            "diff-check", proposal.model_dump_json(), "FP_WARP_SIZE", self.analysis, used_lines,
        )

    async def test_valid_context_variants_and_numeric_mistakes_are_canonicalized(self):
        variants = [
            candidate(lines_added=0, lines_deleted=1),
            candidate(WRONG_HUNK_LENGTHS),
            candidate(WRONG_HUNK_LENGTHS, lines_added=0, lines_deleted=0),
            candidate(HEADERS + "@@ -3 +3 @@\n" + REPLACEMENT),
            candidate(engine._SIM_DIFF.replace("\n", "\r\n")),
            candidate(engine._SIM_DIFF.removesuffix("\n")),
            candidate(engine._SIM_DIFF.replace("@@\n", "@@ kernel context\n")),
        ]
        for proposal in variants:
            with self.subTest(diff=proposal.diff, counts=(proposal.lines_added, proposal.lines_deleted)):
                result = await self.validate(proposal)
                self.assertEqual(result.diff, engine._SIM_DIFF)
                self.assertEqual((result.lines_added, result.lines_deleted), (1, 1))
                self.assertEqual(result.patch_id, proposal.patch_id)
                self.assertEqual(result.explanation, proposal.explanation)
                self.assertEqual(PatchProposal.model_validate_json(result.model_dump_json()), result)
        self.assertTrue(any(
            "canonicalized" in call.args[0].message for call in self.broadcast.await_args_list
        ))

    async def test_appended_source_and_malformed_or_ambiguous_bodies_are_rejected(self):
        small = HEADERS + "@@ -3 +3 @@\n" + REPLACEMENT
        invalid = [
            engine._SIM_DIFF + "".join(engine._SIM_SOURCE),
            engine._SIM_DIFF + "\n" + "".join(engine._SIM_SOURCE),
            engine._SIM_DIFF + "\nExplanation: this should pass.\n",
            engine._SIM_DIFF + HEADERS + "@@ -3 +3 @@\n" + REPLACEMENT,
            "```diff\n" + engine._SIM_DIFF + "```\n",
            engine._SIM_DIFF.replace("--- a/csrc/elementwise.cu", "--- a/../outside.cu"),
            engine._SIM_DIFF.replace("+++ b/csrc/elementwise.cu", "+++ b/setup.py"),
            engine._SIM_DIFF.replace("-1,6 +1,6", "-2,6 +2,6"),
            engine._SIM_DIFF.replace("-1,6 +1,6", "-1,6 +2,6"),
            engine._SIM_DIFF.replace("-    const int threads = 32;", "-    const int threads = 16;"),
            small + "@@ -3 +3 @@\n" + REPLACEMENT,
            engine._SIM_DIFF + "@@ -7 +7 @@\n " + engine._SIM_SOURCE[6],
            engine._SIM_DIFF + "\x00",
            engine._SIM_DIFF.replace("\n", "\r"),
            HEADERS,
        ]
        for diff in invalid:
            with self.subTest(diff=diff):
                with self.assertRaises(ValueError):
                    await self.validate(candidate(diff))

    async def test_applicable_unauthorized_source_change_is_still_rejected_by_policy(self):
        proposal = candidate(engine._SIM_DIFF.replace("+    const int threads = warpSize;", "+    const int threads = 64;"))
        with patch.object(engine, "_run_patch_check_step", wraps=engine._run_patch_check_step) as check:
            with self.assertRaisesRegex(ValueError, "Policy rejected"):
                await self.validate(proposal)
        check.assert_awaited_once()

    async def test_redundant_delete_and_add_cannot_disappear_from_policy_checks(self):
        include = engine._SIM_SOURCE[0]
        proposal = candidate(engine._SIM_DIFF.replace(" " + include, "-" + include + "+" + include))
        canonical, added, deleted = engine._canonicalize_simulated_diff(proposal)
        self.assertEqual(canonical, engine._SIM_DIFF)
        self.assertEqual((added, deleted), (2, 2))
        with self.assertRaisesRegex(ValueError, "Policy rejected"):
            await self.validate(proposal)

    async def test_actual_operations_enforce_single_patch_budget_despite_low_metadata(self):
        body = ""
        for index, line in enumerate(engine._SIM_SOURCE[:61]):
            replacement = "    const int threads = warpSize;\n" if index == 2 else line
            body += "-" + line + "+" + replacement
        proposal = candidate(HEADERS + "@@ -1,61 +1,61 @@\n" + body, lines_added=0, lines_deleted=0)
        canonical, added, deleted = engine._canonicalize_simulated_diff(proposal)
        self.assertEqual(canonical, engine._SIM_DIFF)
        self.assertEqual((added, deleted), (61, 61))
        with self.assertRaisesRegex(ValueError, "budget"):
            await self.validate(proposal)

    async def test_computed_counts_enforce_cumulative_budget(self):
        with self.assertRaisesRegex(ValueError, "budget"):
            await self.validate(candidate(lines_added=0, lines_deleted=0), used_lines=11)

    async def test_schema_allowlist_and_fingerprint_still_precede_applicability(self):
        invalid = [
            {"lines_added": "1"}, {"lines_deleted": True}, {"lines_added": 121},
            {"modifies_dependencies": True}, {"modifies_public_api": True},
            {"modifies_tests_or_tolerances": True}, {"allowlisted": False},
            {"file_path": "../outside.cu"}, {"fingerprint_id": "FP_UNKNOWN"},
            {"unexpected": "value"},
        ]
        for changes in invalid:
            with self.subTest(changes=changes), patch.object(engine, "_run_patch_check_step", new_callable=AsyncMock) as check:
                raw = json.dumps({**candidate().model_dump(), **changes})
                with self.assertRaises(ValueError):
                    await engine._validate_patch("diff-check", raw, "FP_WARP_SIZE", self.analysis, 0)
                check.assert_not_awaited()

    async def test_repaired_metadata_reaches_simulated_application_without_gpu_success(self):
        raw = candidate(WRONG_HUNK_LENGTHS, lines_added=0, lines_deleted=1).model_dump_json()
        with patch.object(engine, "_propose_patch", new_callable=AsyncMock, return_value=raw), patch.object(
            engine, "_run_apply_patch_step", wraps=engine._run_apply_patch_step,
        ) as apply:
            final = await engine.run_migration_pipeline("normalized-demo", JobCreateRequest(repo_path="unused"))
        apply.assert_awaited_once()
        accepted = apply.await_args.args[1]
        self.assertEqual(accepted.diff, engine._SIM_DIFF)
        self.assertEqual((accepted.lines_added, accepted.lines_deleted), (1, 1))
        self.assertEqual(final.repair_rounds_used, 1)
        self.assertEqual(final.current_state, PipelineState.ROLLED_BACK)
        self.assertEqual(final.verification_report.overall_status, "FAILED")
        self.assertFalse(final.verification_report.cpu_reference_verified)
        self.assertTrue(any(
            isinstance(call.args[0].data, PatchProposal) and "accepted" in call.args[0].message
            for call in self.broadcast.await_args_list
        ))


if __name__ == "__main__":
    unittest.main()
