"""Git worktree manager for agent runs.

A single worktree is created per run (`run-{id}`) and shared sequentially
by planner, coder, and tester roles.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional


class WorktreeManager:
    """Manages a single git worktree per run."""

    def __init__(self, base_dir: str, run_id: int):
        self.run_id = run_id
        self.base_dir = Path(base_dir)
        self.worktrees_dir = self.base_dir / ".worktrees"
        self._ensure_worktrees_dir()

    def _ensure_worktrees_dir(self):
        """Ensure .worktrees directory exists and is git-ignored."""
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        gitignore = self.base_dir / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if ".worktrees/" not in content and ".worktrees" not in content:
                with open(gitignore, "a") as f:
                    f.write("\n.worktrees/\n")

    @property
    def worktree_path(self) -> Path:
        """Path to the single worktree for this run."""
        return self.worktrees_dir / f"run-{self.run_id}"

    @property
    def branch_name(self) -> str:
        """Git branch name for this run."""
        return f"agent/run-{self.run_id}"

    def create(self, source_branch: str = "master") -> Path:
        """Create a single git worktree for this run.

        Args:
            source_branch: The base branch to create the worktree from

        Returns:
            Path to the worktree directory
        """
        path = self.worktree_path
        if path.exists():
            self.remove()

        result = subprocess.run(
            ["git", "worktree", "add", str(path), "-b", self.branch_name],
            cwd=str(self.base_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["git", "worktree", "add", str(path), self.branch_name],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        return path

    def remove(self):
        """Remove the git worktree and branch for this run."""
        path = self.worktree_path
        if not path.exists():
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=str(self.base_dir),
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "branch", "-D", self.branch_name],
            cwd=str(self.base_dir),
            capture_output=True,
            text=True,
        )

    def commit(self, message: str, files: Optional[list] = None):
        """Commit changes in the worktree.

        Args:
            message: Commit message
            files: Optional list of specific files to commit. If None, commits all changes.
        """
        path = self.worktree_path
        if not path.exists():
            raise ValueError("Worktree does not exist")

        subprocess.run(
            ["git", "config", "user.email", "agent@multi-agent-studio.ai"],
            cwd=str(path),
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Multi-Agent Bot"],
            cwd=str(path),
            capture_output=True,
            text=True,
        )

        if files:
            for f in files:
                subprocess.run(
                    ["git", "add", f],
                    cwd=str(path),
                    capture_output=True,
                    text=True,
                )
        else:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(path),
                capture_output=True,
                text=True,
            )

        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(path),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def read_file(self, file_path: str) -> str:
        """Read a file from the worktree.

        Args:
            file_path: Relative path within the worktree

        Returns:
            File contents
        """
        full = self.worktree_path / file_path
        return full.read_text() if full.exists() else f"File {file_path} not found"

    def write_file(self, file_path: str, content: str):
        """Write a file in the worktree.

        Args:
            file_path: Relative path within the worktree
            content: File contents to write
        """
        full = self.worktree_path / file_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
