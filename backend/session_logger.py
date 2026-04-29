"""Session logging — persists run steps and auto-generates CHANGELOG.md."""

import json
import textwrap
from pathlib import Path
from typing import Optional, List

import aiosqlite


class SessionLogger:
    """Logs each step to DB and auto-generates CHANGELOG.md"""

    def __init__(self, worktree_path: str, db_path: str, run_id: int):
        self.worktree_path = Path(worktree_path)
        self.db_path = db_path
        self.run_id = run_id
        self.changelog_path = self.worktree_path / "CHANGELOG.md"

    async def log_step(
        self,
        step_number: int,
        role: str,
        step_type: str,
        input_data: str,
        output_data: Optional[str],
        latency_ms: int,
        error: Optional[str],
        files_changed: Optional[List[str]] = None,
        git_commit: Optional[str] = None,
    ) -> None:
        """Persist a step to the DB and append a summary to CHANGELOG.md."""
        # Summarise fields for the DB (store full data in output but keep it raw)
        agent = self._extract_agent_name(output_data) or role

        files_changed_json = json.dumps(files_changed or [])

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO run_steps
                    (run_id, step_number, step_type, phase, agent, input, output,
                     latency_ms, error, files_changed, git_commit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    step_number,
                    step_type,
                    role,
                    agent,
                    input_data,
                    output_data,
                    latency_ms,
                    error,
                    files_changed_json,
                    git_commit,
                ),
            )
            await db.commit()

        await self._append_changelog(
            step_number=step_number,
            role=role,
            agent=agent,
            files_changed=files_changed or [],
            git_commit=git_commit,
            output_data=output_data,
            error=error,
        )

    @staticmethod
    def _extract_agent_name(output_data: Optional[str]) -> Optional[str]:
        """Best-effort extraction of an agent identifier from JSON output."""
        if not output_data:
            return None
        try:
            parsed = json.loads(output_data)
            # Prefer an explicit agent/model field if present
            return parsed.get("model_name") or parsed.get("agent") or None
        except Exception:
            return None

    @staticmethod
    def _truncate(value: Optional[str], length: int = 80) -> str:
        if not value:
            return ""
        if len(value) <= length:
            return value
        return value[: length - 1] + "…"

    @staticmethod
    def _summarize_output(output_data: Optional[str]) -> str:
        """Return a human-readable one-line summary from output."""
        if not output_data:
            return "(no output)"
        try:
            parsed = json.loads(output_data)
            summary = parsed.get("summary") or parsed.get("raw_output")
            if summary:
                return SessionLogger._truncate(summary, 200)
        except Exception:
            pass
        return SessionLogger._truncate(output_data, 200)

    async def _append_changelog(
        self,
        step_number: int,
        role: str,
        agent: Optional[str],
        files_changed: List[str],
        git_commit: Optional[str],
        output_data: Optional[str],
        error: Optional[str],
    ) -> None:
        """Append a Markdown entry to CHANGELOG.md."""
        lines: List[str] = []
        display_agent = agent or "unknown"
        heading = f"## Step {step_number} — {role.capitalize()} ({display_agent})"
        lines.append(heading)

        if files_changed:
            files_md = ", ".join(f"`{f}`" for f in files_changed)
            lines.append(f"- Files changed: {files_md}")

        if git_commit:
            lines.append(f"- Commit: `{git_commit}`")

        if error:
            lines.append(f"- Error: {self._truncate(error, 200)}")
        else:
            lines.append(f"- Summary: {self._summarize_output(output_data)}")

        lines.append("")
        entry = "\n".join(lines)

        # Ensure file exists and tack entry on the end
        if self.changelog_path.exists():
            self.changelog_path.write_text(
                self.changelog_path.read_text(encoding="utf-8") + entry,
                encoding="utf-8",
            )
        else:
            self.changelog_path.write_text(entry, encoding="utf-8")
