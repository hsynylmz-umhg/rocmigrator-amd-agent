"""
agent_orchestrator/rollback.py — Best-Known Commit and Rollback Mechanism.
Reverts to the best-known commit if there is no progress for two consecutive rounds
or if compilation regresses.
All subprocess calls are strictly executed with shell=False.
"""

import subprocess
from typing import List, Optional


class RollbackManager:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.best_known_commit: Optional[str] = None
        self.history: List[str] = []
        self.consecutive_stalls: int = 0

    def record_commit(self, commit_hash: str, is_progress: bool = True):
        """Records a new commit."""
        self.history.append(commit_hash)
        if is_progress:
            self.best_known_commit = commit_hash
            self.consecutive_stalls = 0
        else:
            self.consecutive_stalls += 1

    def should_rollback(self) -> bool:
        """Requires rollback if no progress is made for 2 consecutive rounds."""
        return self.consecutive_stalls >= 2

    def execute_rollback(self) -> bool:
        """
        Reverts to the best-known commit.
        Runs with shell=False.
        """
        if not self.best_known_commit:
            return False

        try:
            cmd = ["git", "-C", self.repo_path, "reset", "--hard", self.best_known_commit]
            result = subprocess.run(cmd, shell=False, capture_output=True, text=True, check=True)
            self.consecutive_stalls = 0
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
