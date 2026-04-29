"""Claude Code CLI agent runner.

Replaces raw LLM API calls with Claude Code CLI execution in isolated git worktrees.
Each agent runs Claude Code with a prompt and captures the output.
"""

import os
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Optional


class ClaudeAgentError(Exception):
    """Error running Claude Code agent."""
    pass


class ClaudeAgentRunner:
    """Runs Claude Code CLI as an agent in a specific worktree."""

    def __init__(
        self,
        worktree_path: str,
        role: str,
        allowed_tools: Optional[list] = None,
        max_budget_usd: Optional[float] = None,
    ):
        self.worktree_path = Path(worktree_path)
        self.role = role
        self.allowed_tools = allowed_tools or [
            "Bash",
            "Read",
            "Edit",
            "Write",
            "Agent",
        ]
        self.max_budget_usd = max_budget_usd

    def run(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        """Run Claude Code with a prompt and return structured output.

        Args:
            prompt: The user prompt to send to Claude Code
            system_prompt: Optional system prompt to prepend

        Returns:
            dict with 'output', 'exit_code', 'stdout', 'stderr', 'files_changed'
        """
        # Build the full prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        try:
            # Build Claude Code command
            cmd = [
                "claude",
                "-p",  # Print mode (non-interactive)
                "--dangerously-skip-permissions",  # Skip permission prompts
                "--bare",  # Minimal mode
                "--allowed-tools",
                ",".join(self.allowed_tools),
                "--output-format",
                "text",
            ]

            if self.max_budget_usd:
                cmd.extend(["--max-budget-usd", str(self.max_budget_usd)])

            # Run Claude Code in the worktree with prompt via stdin
            result = subprocess.run(
                cmd,
                cwd=str(self.worktree_path),
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env={
                    **os.environ,
                    "CLAUDE_CODE_SIMPLE": "1",
                },
            )

            # Parse output
            output = result.stdout
            stderr = result.stderr

            # Extract any JSON from the output
            structured_output = self._extract_json(output)

            # Get list of changed files
            files_changed = self._get_changed_files()

            return {
                "output": structured_output or output,
                "raw_output": output,
                "exit_code": result.returncode,
                "stdout": output,
                "stderr": stderr,
                "files_changed": files_changed,
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            raise ClaudeAgentError("Claude Code timed out after 10 minutes")
        except Exception as e:
            raise ClaudeAgentError(f"Failed to run Claude Code: {e}")

    def _extract_json(self, text: str) -> Optional[dict]:
        """Try to extract JSON from Claude Code output."""
        import re

        # Look for JSON code blocks
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Look for raw JSON objects
        json_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def _get_changed_files(self) -> list:
        """Get list of files changed in the worktree."""
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return []

        files = []
        for line in result.stdout.strip().split("\n"):
            if line:
                # Format: " M filename" or "A  filename"
                parts = line.strip().split()
                if len(parts) >= 2:
                    files.append(parts[-1])

        return files

    def read_history(self, n: int = 5) -> str:
        """Read recent git history for context."""
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", str(n)],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else ""

    def read_other_agent_history(self, other_role: str, base_dir: str, n: int = 5) -> str:
        """Read commit history from another agent's branch.

        Args:
            other_role: The role of the other agent ('planner', 'coder', 'tester')
            base_dir: The base directory of the project
            n: Number of commits to show

        Returns:
            Formatted git log output
        """
        branch_name = f"agent/run-{self.role.split('/')[-1] if '/' in self.role else 'unknown'}-{other_role}"

        # Fetch the other agent's branch
        result = subprocess.run(
            ["git", "fetch", "origin", branch_name],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )

        # Show log of the other branch
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", str(n), f"origin/{branch_name}"],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )

        return result.stdout if result.returncode == 0 else f"Could not read history from {other_role}"
