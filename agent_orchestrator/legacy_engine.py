"""
agent_orchestrator/engine.py — Explicit Python State Machine Main Loop.
LangChain is NOT USED.
State transitions:
CREATED → CLONING → SECURITY_SCAN → ANALYSIS → BASELINE → HIPIFICATION →
COMPILING ↔ REPAIR → VERIFYING → BENCHMARKING → REPORT → USER_APPROVAL →
PR_CREATED | ROLLED_BACK

Git commits are created at each step of progress.
Rollback is triggered if there is no progress for 2 consecutive rounds.
All subprocess calls are executed with shell=False.
"""

import os
import subprocess
from typing import Callable, Dict, List, Optional

from contracts.state_schemas import PipelineState, StateTransitionEvent
from contracts.verification_schemas import VerificationReport
from contracts.api_schemas import LogEvent
from agent_orchestrator.fingerprints.db import FingerprintDB
from agent_orchestrator.policies.patch_policy import PatchPolicy
from agent_orchestrator.rollback import RollbackManager
from agent_orchestrator.states.handlers import StateHandlers


class OrchestratorEngine:
    def __init__(
        self,
        job_id: str,
        repo_path: str,
        target_branch: str = "hip-port",
        log_callback: Optional[Callable[[LogEvent], None]] = None,
    ):
        self.job_id = job_id
        self.repo_path = os.path.abspath(repo_path)
        self.target_branch = target_branch
        self.log_callback = log_callback

        self.current_state = PipelineState.CREATED
        self.fingerprint_db = FingerprintDB()
        self.patch_policy = PatchPolicy()
        self.rollback_mgr = RollbackManager(self.repo_path)
        self.handlers = StateHandlers(
            self.repo_path, self.fingerprint_db, self.patch_policy, self.rollback_mgr
        )

        self.repair_round = 0
        self.max_repair_rounds = 6
        self.verification_report: Optional[VerificationReport] = None
        self.pr_info: Optional[Dict] = None

    def emit_log(self, level: str, message: str, data: Optional[Dict] = None):
        event = LogEvent(
            job_id=self.job_id,
            level=level,
            state=self.current_state,
            message=message,
            data=data or {},
        )
        if self.log_callback:
            self.log_callback(event)
        else:
            print(f"[{event.level}][{event.state.value}] {event.message}")

    def git_commit(self, message: str) -> Optional[str]:
        """
        Creates a git commit on each progress step (shell=False).
        """
        try:
            subprocess.run(
                ["git", "-C", self.repo_path, "add", "-A"],
                shell=False,
                capture_output=True,
                check=False,
            )
            res = subprocess.run(
                ["git", "-C", self.repo_path, "commit", "-m", message],
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
            # Retrieve commit hash
            hash_res = subprocess.run(
                ["git", "-C", self.repo_path, "rev-parse", "HEAD"],
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
            commit_hash = hash_res.stdout.strip() if hash_res.returncode == 0 else "mock_hash"
            self.rollback_mgr.record_commit(commit_hash, is_progress=True)
            return commit_hash
        except Exception:
            return None

    def run_pipeline(self, user_approval_granted: bool = True) -> PipelineState:
        """
        Executes the main pipeline loop from start to finish.
        """
        self.emit_log("STEP", "Pipeline initialized: CREATED")

        # 1. CREATED
        ok, msg = self.handlers.handle_created({})
        if not ok:
            self.emit_log("ERROR", f"CREATED error: {msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state

        # 2. CLONING
        self.current_state = PipelineState.CLONING
        self.emit_log("STEP", "State: CLONING")
        ok, msg = self.handlers.handle_cloning({})
        if not ok:
            self.emit_log("ERROR", f"CLONING error: {msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state

        # 3. SECURITY_SCAN
        self.current_state = PipelineState.SECURITY_SCAN
        self.emit_log("STEP", "State: SECURITY_SCAN")
        ok, msg = self.handlers.handle_security_scan({})
        if not ok:
            self.emit_log("ERROR", f"SECURITY_SCAN error: {msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state
        self.emit_log("INFO", msg)

        # 4. ANALYSIS
        self.current_state = PipelineState.ANALYSIS
        self.emit_log("STEP", "State: ANALYSIS")
        ok, msg, info = self.handlers.handle_analysis({})
        if not ok:
            self.emit_log("ERROR", f"ANALYSIS error: {msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state
        self.emit_log("INFO", msg, info)

        # 5. BASELINE
        self.current_state = PipelineState.BASELINE
        self.emit_log("STEP", "State: BASELINE")
        ok, msg = self.handlers.handle_baseline({})
        if not ok:
            self.emit_log("ERROR", f"BASELINE error: {msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state
        self.emit_log("INFO", msg)
        self.git_commit("checkpoint: BASELINE verified")

        # 6. HIPIFICATION
        self.current_state = PipelineState.HIPIFICATION
        self.emit_log("STEP", "State: HIPIFICATION")
        ok, msg = self.handlers.handle_hipification({})
        if not ok:
            self.emit_log("ERROR", f"HIPIFICATION error: {msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state
        self.emit_log("INFO", msg)
        self.git_commit("checkpoint: HIPIFICATION applied")

        # 7. COMPILING ↔ REPAIR LOOP
        self.current_state = PipelineState.COMPILING
        self.emit_log("STEP", "State: COMPILING")

        while True:
            compile_ok, comp_msg, comp_err = self.handlers.handle_compiling({})
            if compile_ok:
                self.emit_log("INFO", "Compilation successful.")
                self.git_commit("checkpoint: COMPILING passed")
                break

            # Compilation failed -> transition to REPAIR state
            self.repair_round += 1
            self.current_state = PipelineState.REPAIR
            self.emit_log(
                "WARNING",
                f"Compilation error occurred, initiating REPAIR round {self.repair_round}/{self.max_repair_rounds}: {comp_msg}",
            )

            if self.repair_round > self.max_repair_rounds:
                self.emit_log("ERROR", "Maximum repair round budget exceeded.")
                self.handlers.handle_rolled_back()
                self.current_state = PipelineState.ROLLED_BACK
                return self.current_state

            repair_ok, rep_msg, proposal = self.handlers.handle_repair(comp_err, self.repair_round)
            if not repair_ok:
                self.emit_log("ERROR", f"Repair failed: {rep_msg}")
                self.handlers.handle_rolled_back()
                self.current_state = PipelineState.ROLLED_BACK
                return self.current_state

            self.emit_log("INFO", f"Repair successful: {rep_msg}", proposal.model_dump() if proposal else {})
            self.git_commit(f"repair: round {self.repair_round} - {proposal.patch_id}")

            # Return to compilation
            self.current_state = PipelineState.COMPILING
            self.emit_log("STEP", "Attempting recompilation...")

        # 8. VERIFYING
        self.current_state = PipelineState.VERIFYING
        self.emit_log("STEP", "State: VERIFYING")
        verify_ok, verify_msg, report = self.handlers.handle_verifying({})
        if not verify_ok:
            self.emit_log("ERROR", f"VERIFYING error: {verify_msg}")
            self.handlers.handle_rolled_back()
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state
        self.verification_report = report
        self.emit_log("INFO", f"Numerical verification successful: {verify_msg}")

        # 9. BENCHMARKING
        self.current_state = PipelineState.BENCHMARKING
        self.emit_log("STEP", "State: BENCHMARKING")
        bench_ok, bench_msg, bench_data = self.handlers.handle_benchmarking({})
        self.emit_log("INFO", bench_msg, bench_data)

        # 10. REPORT
        self.current_state = PipelineState.REPORT
        self.emit_log("STEP", "State: REPORT")
        rep_ok, rep_msg, rep_json = self.handlers.handle_report({})
        if not rep_ok:
            self.emit_log("ERROR", f"REPORT error: {rep_msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state
        self.emit_log("INFO", rep_msg)

        # 11. USER_APPROVAL
        self.current_state = PipelineState.USER_APPROVAL
        self.emit_log("STEP", "State: Awaiting USER_APPROVAL...")
        app_ok, app_msg = self.handlers.handle_user_approval(user_approval_granted)
        if not app_ok:
            self.emit_log("WARNING", app_msg)
            self.handlers.handle_rolled_back()
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state
        self.emit_log("INFO", app_msg)

        # 12. PR_CREATED
        self.current_state = PipelineState.PR_CREATED
        self.emit_log("STEP", "State: PR_CREATED")
        pr_ok, pr_msg, pr_data = self.handlers.handle_pr_created({"target_branch": self.target_branch})
        if not pr_ok:
            self.emit_log("ERROR", f"PR_CREATED error: {pr_msg}")
            self.current_state = PipelineState.ROLLED_BACK
            return self.current_state

        self.pr_info = pr_data
        self.emit_log("INFO", pr_msg, pr_data)
        return self.current_state
