"""
agent_orchestrator/rollback.py — Best-Known Commit and Rollback Mechanism.
Reverts to the best-known commit if there is no progress for two consecutive rounds
or if compilation regresses.
All subprocess calls are strictly executed with shell=False.
"""

import subprocess
from pathlib import Path, PurePosixPath
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

    def restore_isolated_files(self, git_dir: str, paths: tuple[str, ...]) -> bool:
        """Restore only checkpointed export files without destructive Git operations.

        The real engine places Git metadata beside, never inside, runner inputs.
        Compilers run in ephemeral containers and cannot create export artifacts.
        """
        if not self.best_known_commit:
            return False
        root = Path(self.repo_path).resolve()
        metadata = Path(git_dir).resolve()
        if metadata.parent != root.parent or metadata == root:
            return False
        try:
            contents: list[tuple[Path, bytes]] = []
            for relative in paths:
                parsed = PurePosixPath(relative)
                target = root / relative
                if (parsed.is_absolute() or ".." in parsed.parts or "\\" in relative
                        or str(parsed) != relative or target.is_symlink()
                        or not target.resolve().is_relative_to(root)):
                    return False
                result = subprocess.run(
                    ["git", f"--git-dir={metadata}", "show", f"{self.best_known_commit}:{relative}"],
                    shell=False, capture_output=True, timeout=30, check=True,
                )
                contents.append((target, result.stdout))
            for target, content in contents:
                target.write_bytes(content)
            result = subprocess.run(
                ["git", f"--git-dir={metadata}", f"--work-tree={root}", "-c", "core.bare=false",
                 "-c", "core.autocrlf=false", "diff", "--quiet", self.best_known_commit, "--"],
                shell=False, capture_output=True, timeout=30, check=False,
            )
            if result.returncode == 0:
                self.consecutive_stalls = 0
                return True
            return False
        except (OSError, ValueError, subprocess.SubprocessError):
            return False
