"""OpenCode CLI agent runner.

Replaces raw LLM API calls with OpenCode CLI execution in isolated git worktrees.
Each agent runs OpenCode with a prompt and captures the output.
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Optional


class OpenCodeAgentError(Exception):
    """Error running OpenCode agent."""
    pass


class OpenCodeAgentRunner:
    """Runs OpenCode CLI as an agent in a specific worktree."""

    def __init__(
        self,
        worktree_path: str,
        role: str,
        allowed_tools: Optional[list] = None,
        max_budget_usd: Optional[float] = None,
        model: Optional[str] = None,
    ):
        self.worktree_path = Path(worktree_path)
        self.role = role
        # allowed_tools and max_budget_usd are kept for API compatibility but
        # are not passed to opencode (not supported by the CLI).
        self.allowed_tools = allowed_tools or [
            "Bash",
            "Read",
            "Edit",
            "Write",
            "Agent",
        ]
        self.max_budget_usd = max_budget_usd
        self.model = model

    def run(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        """Run OpenCode with a prompt and return structured output.

        Args:
            prompt: The user prompt to send to OpenCode
            system_prompt: Optional system prompt to prepend

        Returns:
            dict with 'output', 'exit_code', 'stdout', 'stderr', 'files_changed'
        """
        # Build the full prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        try:
            # Build OpenCode command
            # Note: opencode uses `run` subcommand for non-interactive execution.
            # The `-p` flag in opencode is `--password`, not print mode.
            # Flags preserved from Claude Agent that opencode supports:
            #   --dangerously-skip-permissions
            # Flags removed because unsupported by opencode:
            #   --bare
            #   --allowed-tools
            #   --output-format (opencode has --format default|json, omitted)
            #   --max-budget-usd
            cmd = [
                "opencode",
                "run",
                "--dangerously-skip-permissions",  # Auto-approve permissions
            ]

            if self.model:
                cmd.extend(["--model", self.model])

            # Run OpenCode in the worktree with prompt as a positional arg
            result = subprocess.run(
                cmd + [full_prompt],
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env={
                    **os.environ,
                    "OPENCODE_SIMPLE": "1",
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
            raise OpenCodeAgentError("OpenCode timed out after 10 minutes")
        except Exception as e:
            raise OpenCodeAgentError(f"Failed to run OpenCode: {e}")

    def _extract_json(self, text: str) -> Optional[dict]:
        """Try to extract JSON from OpenCode output."""
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

    def read_git_history(self, n: int = 5) -> str:
        """Read recent git history for context."""
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", str(n)],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else ""

    # Backwards-compatible alias for read_git_history
    read_history = read_git_history

    def get_git_diff(self, since_ref: str) -> str:
        """Get git diff since a specific reference."""
        result = subprocess.run(
            ["git", "diff", since_ref],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else ""

    def read_other_agent_history(self, other_role: str, base_dir: str, n: int = 5) -> str:
        """Read commit history from the shared worktree branch.

        Since all roles now share a single worktree, this simply returns the
        recent git history of the current branch.

        Args:
            other_role: Ignored (kept for backward compatibility)
            base_dir: Ignored (kept for backward compatibility)
            n: Number of commits to show

        Returns:
            Formatted git log output
        """
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", str(n)],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else f"Could not read history from shared branch"
