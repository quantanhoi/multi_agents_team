"""Git worktree manager for agent isolation.

Each agent (planner, coder, tester) gets its own git worktree so they can:
- Work in isolation without interfering with each other
- Read commit history from other agents
- Commit their own changes after each phase
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional


class WorktreeManager:
    """Manages git worktrees per run and per agent role."""

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

    def _worktree_path(self, role: str) -> Path:
        """Get the worktree path for a given role."""
        return self.worktrees_dir / f"run-{self.run_id}-{role}"

    def _branch_name(self, role: str) -> str:
        """Get the git branch name for a given role."""
        return f"agent/run-{self.run_id}-{role}"

    def create_worktree(self, role: str, source_branch: str = "master") -> Path:
        """Create a git worktree for an agent.

        Args:
            role: One of 'planner', 'coder', 'tester'
            source_branch: The base branch to create the worktree from

        Returns:
            Path to the worktree directory
        """
        worktree_path = self._worktree_path(role)
        branch_name = self._branch_name(role)

        # Remove existing worktree if it exists
        if worktree_path.exists():
            self.remove_worktree(role)

        # Create the worktree
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "-b", branch_name],
            cwd=str(self.base_dir),
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Branch might already exist, try with just the path
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to create worktree for {role}: {result.stderr}"
                )

        return worktree_path

    def remove_worktree(self, role: str):
        """Remove a git worktree for an agent."""
        worktree_path = self._worktree_path(role)
        if not worktree_path.exists():
            return

        # Remove the worktree via git
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=str(self.base_dir),
            capture_output=True,
            text=True,
        )

        # Also delete the branch
        branch_name = self._branch_name(role)
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=str(self.base_dir),
            capture_output=True,
            text=True,
        )

    def get_worktree_path(self, role: str) -> Optional[Path]:
        """Get the path to an agent's worktree."""
        path = self._worktree_path(role)
        return path if path.exists() else None

    def commit(self, role: str, message: str, files: Optional[list] = None):
        """Commit changes in an agent's worktree.

        Args:
            role: One of 'planner', 'coder', 'tester'
            message: Commit message
            files: Optional list of specific files to commit. If None, commits all changes.
        """
        worktree_path = self._worktree_path(role)
        if not worktree_path.exists():
            raise ValueError(f"Worktree for {role} does not exist")

        # Configure git user for this worktree if not set
        subprocess.run(
            ["git", "config", "user.email", f"{role}@multi-agent-studio.ai"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", f"Agent {role.capitalize()}"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
        )

        # Stage files
        if files:
            for f in files:
                subprocess.run(
                    ["git", "add", f],
                    cwd=str(worktree_path),
                    capture_output=True,
                    text=True,
                )
        else:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
            )

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
        )

        return result.returncode == 0

    def get_commit_history(self, role: str, n: int = 10) -> str:
        """Get commit history for an agent's worktree.

        Args:
            role: One of 'planner', 'coder', 'tester'
            n: Number of commits to show

        Returns:
            Formatted git log output
        """
        worktree_path = self._worktree_path(role)
        if not worktree_path.exists():
            return f"Worktree for {role} does not exist"

        result = subprocess.run(
            ["git", "log", "--oneline", "-n", str(n)],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
        )

        return result.stdout if result.returncode == 0 else result.stderr

    def get_diff_from_base(self, role: str) -> str:
        """Get diff between agent's branch and the base branch.

        Args:
            role: One of 'planner', 'coder', 'tester'

        Returns:
            Git diff output
        """
        worktree_path = self._worktree_path(role)
        if not worktree_path.exists():
            return f"Worktree for {role} does not exist"

        result = subprocess.run(
            ["git", "diff", "master...HEAD"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
        )

        return result.stdout if result.returncode == 0 else result.stderr

    def read_file(self, role: str, file_path: str) -> str:
        """Read a file from an agent's worktree.

        Args:
            role: One of 'planner', 'coder', 'tester'
            file_path: Relative path within the worktree

        Returns:
            File contents
        """
        worktree_path = self._worktree_path(role)
        full_path = worktree_path / file_path

        if not full_path.exists():
            return f"File {file_path} not found in {role} worktree"

        return full_path.read_text()

    def write_file(self, role: str, file_path: str, content: str):
        """Write a file in an agent's worktree.

        Args:
            role: One of 'planner', 'coder', 'tester'
            file_path: Relative path within the worktree
            content: File contents to write
        """
        worktree_path = self._worktree_path(role)
        full_path = worktree_path / file_path

        # Ensure parent directories exist
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    def cleanup_all(self):
        """Remove all worktrees for this run."""
        for role in ["planner", "coder", "tester"]:
            self.remove_worktree(role)
