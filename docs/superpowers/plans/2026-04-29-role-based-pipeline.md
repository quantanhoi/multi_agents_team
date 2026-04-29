# Role-Based Synchronous Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the orchestrator from parallel-review/sequential-execution to a strictly sequential role-based pipeline with dynamic assignment, single shared worktree, session logging, and new frontend UI.

**Architecture:** Sequential Planner→Coder→Tester→Planner loop with stateless per-step opencode spawning. Single git worktree per run (`run-{id}`) shared by all roles. Orchestrator assembles full context from run_steps + CHANGELOG.md + git diff before each step.

**Tech Stack:** FastAPI, SQLite, aiosqlite, React 18 + Vite + Tailwind, WebSocket, subprocess-based opencode CLI

---

## File Map

| File | Responsibility |
|------|--------------|
| `backend/opencode_agent.py` | Runs `opencode` CLI as a subprocess per step |
| `backend/worktree_manager.py` | Git worktree creation (single per run) + commit/read helpers |
| `backend/database.py` | SQLite schema — extended `run_steps` + `jobs` |
| `backend/models.py` | Pydantic models — add `DoD`, `step_number` fields |
| `backend/orchestrator.py` | Refactored sequential pipeline engine |
| `backend/routers/runs.py` | New endpoints: `/steps`, `/changelog`; updated `/human_response` |
| `frontend/src/pages/RunPage.tsx` | Restructured layout: PhaseTimeline + ActiveStep + History + HumanInput |
| `frontend/src/components/PhaseTimeline.tsx` | Horizontal step badges (already exists, extend) |
| `frontend/src/components/ActiveStepPanel.tsx` | **New** — shows current role + streaming output + override input |
| `frontend/src/components/HistoryPanel.tsx` | **New** — collapsible list of past steps |
| `frontend/src/components/HumanInputPanel.tsx` | **New** — disabled by default; activates on escalation |
| `frontend/src/types.ts` | Extend TypeScript interfaces for new step/event types |
| `frontend/src/api.ts` | Add `getRunSteps(runId)`, `getRunChangelog(runId)` |

---

## Task 1: Create `OpenCodeAgentRunner` (backend)

**Files:**
- Create: `backend/opencode_agent.py`
- Delete: `backend/claude_agent.py` (after verifying no other imports)
- Modify: `backend/orchestrator.py` (import change)

### Step 1: Write OpenCodeAgentRunner

- [ ] **Step 1.1: Create `opencode_agent.py`**

```python
"""OpenCode CLI agent runner.

Replaces Claude Code CLI with opencode CLI in isolated git worktrees.
Each agent runs opencode with a prompt and captures the output.
"""

import os
import subprocess
import json
import re
from pathlib import Path
from typing import Optional


class OpenCodeAgentError(Exception):
    """Error running opencode agent."""
    pass


class OpenCodeAgentRunner:
    """Runs opencode CLI as an agent in a specific worktree."""

    def __init__(
        self,
        worktree_path: str,
        role: str,
        model: str = "glm5.1",
        allowed_tools: Optional[list] = None,
        max_budget_usd: Optional[float] = None,
    ):
        self.worktree_path = Path(worktree_path)
        self.role = role
        self.model = model
        self.allowed_tools = allowed_tools or [
            "Bash",
            "Read",
            "Edit",
            "Write",
            "Agent",
        ]
        self.max_budget_usd = max_budget_usd

    def run(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        try:
            cmd = [
                "opencode",
                "-p",
                "--model", self.model,
                "--dangerously-skip-permissions",
                "--bare",
                "--allowed-tools",
                ",".join(self.allowed_tools),
                "--output-format",
                "text",
            ]

            if self.max_budget_usd:
                cmd.extend(["--max-budget-usd", str(self.max_budget_usd)])

            result = subprocess.run(
                cmd,
                cwd=str(self.worktree_path),
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=600,
            )

            output = result.stdout
            structured_output = self._extract_json(output)
            files_changed = self._get_changed_files()

            return {
                "output": structured_output or output,
                "raw_output": output,
                "exit_code": result.returncode,
                "stdout": output,
                "stderr": result.stderr,
                "files_changed": files_changed,
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            raise OpenCodeAgentError("opencode timed out after 10 minutes")
        except Exception as e:
            raise OpenCodeAgentError(f"Failed to run opencode: {e}")

    def _extract_json(self, text: str) -> Optional[dict]:
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        json_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def _get_changed_files(self) -> list:
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
                parts = line.strip().split()
                if len(parts) >= 2:
                    files.append(parts[-1])
        return files

    def read_git_history(self, n: int = 3) -> str:
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", str(n)],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else ""

    def get_git_diff(self, since_ref: str = "HEAD~1") -> str:
        result = subprocess.run(
            ["git", "diff", since_ref, "HEAD"],
            cwd=str(self.worktree_path),
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else ""
```

- [ ] **Step 1.2: Update `orchestrator.py` imports**

Replace:
```python
from claude_agent import ClaudeAgentRunner, ClaudeAgentError
```
With:
```python
from opencode_agent import OpenCodeAgentRunner, OpenCodeAgentError
```

- [ ] **Step 1.3: Delete `backend/claude_agent.py`**

```bash
rm backend/claude_agent.py
```

- [ ] **Step 1.4: Commit**

```bash
git add backend/opencode_agent.py backend/orchestrator.py
git rm backend/claude_agent.py
git commit -m "refactor: replace ClaudeAgentRunner with OpenCodeAgentRunner"
```

---

## Task 2: Simplify `WorktreeManager` to Single Worktree Per Run

**Files:**
- Modify: `backend/worktree_manager.py`

### Step 2: Refactor WorktreeManager

- [ ] **Step 2.1: Modify `worktree_manager.py`**

Replace class body to support single worktree per run:

```python
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
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        gitignore = self.base_dir / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if ".worktrees/" not in content and ".worktrees" not in content:
                with open(gitignore, "a") as f:
                    f.write("\n.worktrees/\n")

    @property
    def worktree_path(self) -> Path:
        return self.worktrees_dir / f"run-{self.run_id}"

    @property
    def branch_name(self) -> str:
        return f"agent/run-{self.run_id}"

    def create(self, source_branch: str = "master") -> Path:
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
        path = self.worktree_path
        if not path.exists():
            raise ValueError("Worktree does not exist")

        subprocess.run(
            ["git", "config", "user.email", f"agent@multi-agent-studio.ai"],
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
        full = self.worktree_path / file_path
        return full.read_text() if full.exists() else f"File {file_path} not found"

    def write_file(self, file_path: str, content: str):
        full = self.worktree_path / file_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
```

- [ ] **Step 2.2: Commit**

```bash
git add backend/worktree_manager.py
git commit -m "refactor: simplify WorktreeManager to single shared worktree per run"
```

---

## Task 3: Extend Database Schema

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/models.py` (for `definition_of_done`, `step_number`)

### Step 3.1: Extend `run_steps` table schema

- [ ] **Modify `backend/database.py`** add `step_number`, `step_type`, `files_changed`, `git_commit` columns.

```python
# In init_db or schema definition, extend run_steps:
"""
CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    step_number INTEGER,
    step_type TEXT,
    phase TEXT,
    agent TEXT,
    input TEXT,
    output TEXT,
    latency_ms INTEGER,
    error TEXT,
    files_changed TEXT,
    git_commit TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
"""
```

If using `init_db` function that creates tables, add a migration path or drop-recreate for dev.

- [ ] **Modify `backend/database.py`** add `definition_of_done` to `jobs`:

```python
# Add column to jobs table schema or migration
sql_add_dod = "ALTER TABLE jobs ADD COLUMN definition_of_done TEXT DEFAULT '';"
```

For SQLite migrations in dev, create a `migrate_database()` function that runs `ALTER TABLE` statements wrapped in `try/except` to ignore errors if columns already exist.

### Step 3.2: Extend `models.py`

- [ ] **Modify `backend/models.py`**

Add to `JobCreate`:
```python
class JobCreate(BaseModel):
    # ... existing fields ...
    definition_of_done: str = ""  # NEW
```

Add to `JobResponse`:
```python
class JobResponse(BaseModel):
    # ... existing fields ...
    definition_of_done: str
```

Add new Pydantic model for run steps (used by API):
```python
class StepOut(BaseModel):
    id: int
    run_id: int
    step_number: int
    step_type: str
    phase: str
    agent: str
    input: str
    output: Optional[str]
    latency_ms: int
    error: Optional[str]
    files_changed: Optional[str]
    git_commit: Optional[str]
    created_at: str
```

- [ ] **Step 3.3: Commit**

```bash
git add backend/database.py backend/models.py
git commit -m "feat: extend db schema for step tracking and DoD"
```

---

## Task 4: Add `RoleResolver` and `SessionLogger`

**Files:**
- Create: `backend/role_resolver.py`
- Create: `backend/session_logger.py`

### Step 4.1: RoleResolver

- [ ] **Create `backend/role_resolver.py`**

```python
from typing import Optional
from models import AgentResponse


class RoleResolver:
    """Maps a role (planner/coder/tester) to a configured agent."""

    def __init__(self, agents: dict[int, AgentResponse], job: dict):
        self.agents = agents
        self.job = job

    def assign(self, role: str) -> AgentResponse:
        col = {
            "planner": self.job.get("planner_agent_id"),
            "coder": self.job.get("coder_agent_id"),
            "tester": self.job.get("tester_agent_id"),
        }.get(role)

        if not col or col not in self.agents:
            raise ValueError(f"No agent configured for role: {role}")
        return self.agents[col]
```

### Step 4.2: SessionLogger

- [ ] **Create `backend/session_logger.py`**

```python
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone


class SessionLogger:
    """Logs each step to DB and auto-generates CHANGELOG.md"""

    def __init__(self, worktree_path: str, db_path: str):
        self.worktree_path = Path(worktree_path)
        self.db_path = db_path
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
        files_changed: Optional[list] = None,
        git_commit: Optional[str] = None,
    ):
        import aiosqlite
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO run_steps
            (run_id, step_number, step_type, phase, agent, input, output, latency_ms, error, files_changed, git_commit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ...
        )
        await db.commit()
        await db.close()

        self._append_changelog(step_number, role, files_changed, git_commit, output_data)

    def _append_changelog(self, step_number: int, role: str, files_changed: list, git_commit: Optional[str], output_data: Optional[str]):
        lines = [f"\n## Step {step_number} — {role.capitalize()}", ""]
        if files_changed:
            lines.append(f"- Files changed: {', '.join(files_changed)}")
        if git_commit:
            lines.append(f"- Commit: `{git_commit}`")
        # Try to derive a short summary from output JSON
        summary = ""
        if output_data:
            try:
                out = json.loads(output_data)
                summary = out.get("summary", out.get("raw_output", "")[:80])
            except:
                summary = output_data[:80]
        if summary:
            lines.append(f"- Summary: {summary}")
        content = "\n".join(lines)
        with open(self.changelog_path, "a") as f:
            f.write(content + "\n")
```

- [ ] **Step 4.3: Commit**

```bash
git add backend/role_resolver.py backend/session_logger.py
git commit -m "feat: add RoleResolver and SessionLogger"
```

---

## Task 5: Refactor `orchestrator.py` to Sequential Pipeline

**Files:**
- Modify: `backend/orchestrator.py`

### Step 5.1: Rewrite the Orchestrator class

- [ ] **Modify `backend/orchestrator.py`**

```python
import json
import os
import subprocess
import asyncio
import time
import shutil
from datetime import datetime, timezone
from database import DB_PATH
from websocket import ws_manager
from opencode_agent import OpenCodeAgentRunner, OpenCodeAgentError
from worktree_manager import WorktreeManager
from role_resolver import RoleResolver
from session_logger import SessionLogger
import aiosqlite


class Orchestrator:
    def __init__(self, run_id: int, job_config: dict):
        self.run_id = run_id
        self.job = job_config
        self.overrides = json.loads(job_config.get("agent_overrides", "{}"))
        self.max_iterations = job_config.get("max_iterations", 10)
        self.definition_of_done = job_config.get("definition_of_done", "")
        self._step_counter = 0
        self._worktree_manager = None
        self._role_resolver = None
        self._logger = None

    async def run(self, feature_request: str, context: dict):
        try:
            if not shutil.which("opencode"):
                raise RuntimeError("opencode CLI not found. Install it first.")

            working_dir = await self._get_setting("working_dir") or "."
            self._worktree_manager = WorktreeManager(working_dir, self.run_id)
            wt_path = self._worktree_manager.create()
            self._logger = SessionLogger(str(wt_path), DB_PATH)

            # Resolve agents from job config
            agents = await self._load_agent_configs()
            self._role_resolver = RoleResolver(agents, self.job)

            current_task = feature_request
            iteration = 0
            done = False

            while not done and iteration < self.max_iterations:
                await self._broadcast({"type": "iteration_start", "iteration": iteration + 1})

                # PLAN
                plan = await self._execute_role("planner", current_task, context, "plan")
                if self._needs_human(plan):
                    plan = await self._wait_for_human(plan)
                    if plan.get("_human_aborted"):
                        await self._update_status("failed")
                        return

                # CODE
                code_result = await self._execute_role("coder", json.dumps(plan), context, "code")
                if self._needs_human(code_result):
                    code_result = await self._wait_for_human(code_result)
                    if code_result.get("_human_aborted"):
                        await self._update_status("failed")
                        return

                # TEST
                test_result = await self._execute_role("tester", json.dumps(code_result), context, "test")
                if self._needs_human(test_result):
                    test_result = await self._wait_for_human(test_result)
                    if test_result.get("_human_aborted"):
                        await self._update_status("failed")
                        return

                # EVALUATE
                eval_result = await self._execute_role(
                    "planner",
                    json.dumps({"plan": plan, "code": code_result, "test": test_result}),
                    context,
                    "evaluate",
                )
                if self._needs_human(eval_result):
                    eval_result = await self._wait_for_human(eval_result)
                    if eval_result.get("_human_aborted"):
                        await self._update_status("failed")
                        return

                done = eval_result.get("action") == "done"
                current_task = eval_result.get("next_task", current_task)
                iteration += 1
                await self._update_iterations(iteration)

            status = "done" if done else "failed"
            await self._update_status(status)
            await self._broadcast({"type": status, "status": status})

        except OpenCodeAgentError as e:
            await self._update_status("failed")
            await self._broadcast({"type": "failed", "status": "failed", "message": str(e)})
            raise
        except Exception as e:
            await self._update_status("failed")
            await self._broadcast({"type": "error", "message": str(e), "retryable": False})
            raise
        finally:
            if self._worktree_manager:
                self._worktree_manager.remove()

    async def _execute_role(self, role: str, input_data: str, context: dict, step_type: str) -> dict:
        self._step_counter += 1
        step_num = self._step_counter

        agent_config = self._role_resolver.assign(role)
        model = self._resolve_override(role, "model_name") or agent_config.model_name
        system_prompt = self._build_context(role, agent_config.system_prompt)

        runner = OpenCodeAgentRunner(
            worktree_path=str(self._worktree_manager.worktree_path),
            role=role,
            model=model,
        )

        await self._update_status(f"{step_type}_{role}")
        await self._broadcast({
            "type": "phase_change",
            "phase": step_type,
            "role": role,
            "model": model,
            "step_number": step_num,
        })

        start = time.time()
        last_error = None
        output = None
        try:
            result = runner.run(input_data, system_prompt=system_prompt)
            latency = int((time.time() - start) * 1000)
            output = result.get("output")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    output = {"raw_output": output}

            # Commit changes if any
            if result.get("files_changed"):
                self._worktree_manager.commit(f"Step {step_num}: {role} changes")

            # Update CHANGELOG
            await self._logger.log_step(
                step_num, role, step_type, input_data, json.dumps(output),
                latency, None, result.get("files_changed"), None
            )

            await self._broadcast({
                "type": "agent_output",
                "step_number": step_num,
                "role": role,
                "output": output,
                "files_changed": result.get("files_changed"),
            })

        except OpenCodeAgentError as e:
            latency = int((time.time() - start) * 1000)
            last_error = str(e)
            await self._logger.log_step(step_num, role, step_type, input_data, None, latency, last_error)
            await self._broadcast({"type": "phase_error", "phase": step_type, "role": role, "message": last_error})
            raise

        return output or {}

    def _build_context(self, role: str, base_system_prompt: str) -> str:
        parts = [f"You are the {role.upper()} for this project."]
        if self.definition_of_done:
            parts.append(f"Project Definition of Done: {self.definition_of_done}")

        # Load CHANGELOG and git diff
        changes = self._worktree_manager.read_file("CHANGELOG.md") if (self._worktree_manager.worktree_path / "CHANGELOG.md").exists() else "No prior steps."
        diff = self._worktree_manager._run_git_cmd(["git", "diff", "HEAD~1", "HEAD"]) if self._step_counter > 1 else ""

        parts.extend([
            "---",
            "Prior context (from CHANGELOG.md):",
            changes,
            "---",
            "Recent code changes (git diff):",
            diff,
            "---",
            "Current step instructions: Provide your output as JSON.",
        ])

        if base_system_prompt:
            parts.insert(0, base_system_prompt)

        return "\n\n".join(parts)

    async def _load_agent_configs(self) -> dict:
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM agents")
        rows = await cursor.fetchall()
        await db.close()
        return {r["id"]: dict(r) for r in rows}

    def _resolve_override(self, role: str, field: str):
        role_overrides = self.overrides.get(role, {})
        return role_overrides.get(field)

    async def _update_status(self, status: str):
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE runs SET status = ?, completed_at = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat() if status in ("done", "failed") else None, self.run_id)
        )
        await db.commit()
        await db.close()
        await ws_manager.send(self.run_id, {"type": "phase_change", "phase": status})

    async def _update_iterations(self, count: int):
        db = await aiosqlite.connect(DB_PATH)
        await db.execute("UPDATE runs SET iterations = ? WHERE id = ?", (count, self.run_id))
        await db.commit()
        await db.close()

    async def _broadcast(self, event: dict):
        await ws_manager.send(self.run_id, event)

    async def _get_setting(self, key: str) -> str:
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT value FROM settings WHERE key = ?", (key,))).fetchone()
        await db.close()
        return row["value"] if row else ""

    def _needs_human(self, output: dict) -> bool:
        if not output or not isinstance(output, dict):
            return False
        req = output.get("human_input_request")
        if req is None:
            return False
        if isinstance(req, str):
            return bool(req.strip())
        return isinstance(req, dict) and bool(req.get("message", "").strip())

    async def _wait_for_human(self, output: dict) -> dict:
        # Preserved from existing code — uses ws_manager events + DB
        # NOTE: in this refactor, the override chat input also feeds into this
        ...
```

- [ ] **Step 5.2: Commit**

```bash
git add backend/orchestrator.py
git commit -m "refactor: sequential role-based pipeline replaces parallel execution"
```

---

## Task 6: Add API Endpoints for Steps and Changelog

**Files:**
- Modify: `backend/routers/runs.py`

### Step 6.1: Add endpoints

- [ ] **Modify `backend/routers/runs.py`** add:

```python
@router.get("/{run_id}/steps")
async def get_run_steps(run_id: int):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_number",
        (run_id,)
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]

@router.get("/{run_id}/changelog")
async def get_run_changelog(run_id: int):
    import shutil
    from pathlib import Path
    worktree = Path(".") / ".worktrees" / f"run-{run_id}"
    changelog = worktree / "CHANGELOG.md"
    if changelog.exists():
        return {"content": changelog.read_text()}
    return {"content": ""}
```

- [ ] **Step 6.2: Commit**

```bash
git add backend/routers/runs.py
git commit -m "feat: add /steps and /changelog endpoints for run history"
```

---

## Task 7: Frontend — Restructure RunPage.tsx

**Files:**
- Modify: `frontend/src/pages/RunPage.tsx`
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/ActiveStepPanel.tsx`
- Create: `frontend/src/components/HistoryPanel.tsx`
- Create: `frontend/src/components/HumanInputPanel.tsx`
- Modify: `frontend/src/api.ts`

### Step 7.1: Extend TypeScript types

- [ ] **Modify `frontend/src/types.ts`**

```typescript
export interface RunStep {
  step_number: number;
  step_type: string;
  agent: string;
  output: any;
  files_changed: string[];
  created_at: string;
}

export interface HumanInputRequest {
  requested_by: string;
  message: string;
  input_type: string;
}
```

### Step 7.2: Add API methods

- [ ] **Modify `frontend/src/api.ts`**

```typescript
export const getRunSteps = (runId: number): Promise<RunStep[]> =>
  api.get(`/runs/${runId}/steps`).then(r => r.data);

export const getRunChangelog = (runId: number): Promise<{ content: string }> =>
  api.get(`/runs/${runId}/changelog`).then(r => r.data);
```

### Step 7.3: Create ActiveStepPanel.tsx

- [ ] **Create `frontend/src/components/ActiveStepPanel.tsx`**

```tsx
import { useState } from "react";

export default function ActiveStepPanel({ step, stream, onOverride }: any) {
  const [override, setOverride] = useState("");

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="px-2 py-1 rounded bg-blue-100 text-blue-800 text-sm font-semibold">
          {step.role?.toUpperCase()}
        </span>
        <span className="text-xs text-gray-500">Step {step.step_number}</span>
        <span className="text-xs text-gray-400">model: {step.model}</span>
      </div>
      <div className="whitespace-pre-wrap text-sm bg-gray-50 rounded p-3 min-h-[120px] max-h-[400px] overflow-y-auto">
        {stream || step.output?.raw_output || "Waiting for output..."}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          className="flex-1 border rounded px-3 py-1 text-sm"
          placeholder="Type override / hint..."
          value={override}
          onChange={(e) => setOverride(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onOverride(override);
              setOverride("");
            }
          }}
        />
        <button
          className="px-3 py-1 bg-gray-800 text-white rounded text-sm"
          onClick={() => { onOverride(override); setOverride(""); }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
```

### Step 7.4: Create HistoryPanel.tsx

- [ ] **Create `frontend/src/components/HistoryPanel.tsx`**

```tsx
import { useState } from "react";

export default function HistoryPanel({ steps }: { steps: any[] }) {
  const [open, setOpen] = useState<number | null>(null);

  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="bg-gray-100 px-4 py-2 font-medium text-sm">History</div>
      <div className="max-h-[300px] overflow-y-auto">
        {steps.length === 0 && (
          <div className="px-4 py-3 text-sm text-gray-400">No steps yet</div>
        )}
        {steps.map((s) => (
          <div key={s.step_number} className="border-b last:border-0">
            <button
              className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50 flex justify-between"
              onClick={() => setOpen(open === s.step_number ? null : s.step_number)}
            >
              <span>Step {s.step_number}: {s.agent}</span>
              <span className="text-gray-400">{s.step_type}</span>
            </button>
            {open === s.step_number && (
              <div className="px-4 pb-3 text-xs text-gray-600 whitespace-pre-wrap">
                {JSON.stringify(s.output, null, 2)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Step 7.5: Create HumanInputPanel.tsx

- [ ] **Create `frontend/src/components/HumanInputPanel.tsx`**

```tsx
import { useState } from "react";

export default function HumanInputPanel({ request, onSubmit }: any) {
  const [response, setResponse] = useState("");

  if (!request) {
    return (
      <div className="border rounded-lg p-4 bg-gray-50 opacity-60">
        <p className="text-sm text-gray-500">Waiting for agent request...</p>
        <input disabled className="mt-2 w-full border rounded px-3 py-1 text-sm" />
        <button disabled className="mt-2 px-3 py-1 bg-gray-300 rounded text-sm">Submit</button>
      </div>
    );
  }

  return (
    <div className="border rounded-lg p-4 bg-yellow-50 shadow-sm">
      <div className="font-medium text-sm mb-1 text-yellow-800">Input Required</div>
      <div className="text-sm mb-3">{request.message}</div>
      <textarea
        className="w-full border rounded px-3 py-2 text-sm min-h-[80px]"
        placeholder="Your response..."
        value={response}
        onChange={(e) => setResponse(e.target.value)}
      />
      <div className="mt-2 flex gap-2">
        <button
          className="px-4 py-1 bg-yellow-600 text-white rounded text-sm"
          onClick={() => { onSubmit(response); setResponse(""); }}
        >
          Submit
        </button>
      </div>
    </div>
  );
}
```

### Step 7.6: Wire into RunPage.tsx

- [ ] **Modify `frontend/src/pages/RunPage.tsx`**

```tsx
// State additions
const [steps, setSteps] = useState<RunStep[]>([]);
const [activeStep, setActiveStep] = useState<Partial<RunStep>>({});
const [humanRequest, setHumanRequest] = useState<HumanInputRequest | null>(null);
const [streamBuffer, setStreamBuffer] = useState("");

// On WebSocket message:
useWebSocket(() => {
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.type === "phase_change") {
      setActiveStep({ role: data.role, step_number: data.step_number, model: data.model });
      setStreamBuffer("");
    }
    if (data.type === "agent_output") {
      setSteps(prev => [...prev, { ...data, step_number: data.step_number }]);
      setStreamBuffer(prev => prev + "\n" + JSON.stringify(data.output));
    }
    if (data.type === "human_input_required") {
      setHumanRequest(data);
    }
  };
});

// JSX layout:
// PhaseTimeline
// ActiveStepPanel step={activeStep} stream={streamBuffer} onOverride={sendOverride}
// HistoryPanel steps={steps}
// HumanInputPanel request={humanRequest} onSubmit={sendHumanResponse}
```

- [ ] **Step 7.7: Commit**

```bash
git add frontend/src/
git commit -m "feat: restructure RunPage with ActiveStep, History, HumanInput panels"
```

---

## Task 8: Integration Test

**Files:**
- Create: `backend/tests/test_pipeline.py`

### Step 8.1: Write integration test

- [ ] **Create `backend/tests/test_pipeline.py`**

```python
import pytest
from orchestrator import Orchestrator

@pytest.mark.asyncio
async def test_sequential_pipeline(mock_db, mock_opencode):
    """Verify planner→coder→tester→planner loop completes."""
    job = {
        "id": 1,
        "planner_agent_id": 1,
        "coder_agent_id": 2,
        "tester_agent_id": 3,
        "agent_overrides": "{}",
        "max_iterations": 3,
        "definition_of_done": "Build a greeting endpoint that returns 'hello'",
    }
    run = Orchestrator(run_id=42, job_config=job)
    result = await run.run("Build a greeting endpoint", {})
    assert result is not None
```

- [ ] **Step 8.2: Commit**

```bash
git add backend/tests/test_pipeline.py
git commit -m "test: add integration test for sequential pipeline"
```

---

## Task 9: Final Cleanup

- [ ] Run backend linter: `cd backend && ruff check .`
- [ ] Run frontend build: `cd frontend && npm run build`
- [ ] Update `docs/PROJECT-STATE-2026-04-28.md` with new architecture summary
- [ ] Commit cleanup

---

## Spec Coverage Checklist

| Spec Section | Task |
|---|---|
| Section 3 — Pipeline & Data Flow | Task 5 |
| Section 4 — Agent Runner & Worktree | Tasks 1, 2 |
| Section 5 — Session Change Log | Tasks 4, 3 |
| Section 6 — Dynamic Role Assignment | Task 4 |
| Section 7 — Definition of Done | Task 5 (orchestrator init), Task 3 (DB) |
| Section 8 — Human-in-the-Loop | Task 7 (frontend), Task 5 (`_wait_for_human`) |
| Section 9 — Frontend UI | Task 7 |
| Section 11 — DB Changes | Task 3 |
| Section 12 — API Changes | Task 6 |
