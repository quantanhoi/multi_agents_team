import json
import os
import subprocess
import asyncio
import time
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
        self.max_iterations = job_config.get("max_iterations", 5)
        self.definition_of_done = job_config.get("definition_of_done", "")
        self._worktree_manager = None
        self._role_resolver = None
        self._session_logger = None
        self._step_number = 0
        self._git_runner = None
        self._base_commit = None

    async def run(self, feature_request: str, context: dict):
        try:
            import shutil
            if not shutil.which("opencode"):
                raise RuntimeError(
                    "OpenCode CLI not found. Install it first: npm install -g opencode"
                )

            working_dir = await self._get_setting("working_dir") or "."
            self._worktree_manager = WorktreeManager(working_dir, self.run_id)

            # Create single shared worktree
            wt_path = self._worktree_manager.create()

            # Resolve base commit for diffing
            ref_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(wt_path),
                capture_output=True,
                text=True,
            )
            self._base_commit = ref_result.stdout.strip() if ref_result.returncode == 0 else "HEAD"

            # Load agents for this job
            agents = await self._load_agents()
            self._role_resolver = RoleResolver(self.job, agents)

            # Initialize session logger
            self._session_logger = SessionLogger(
                worktree_path=str(wt_path),
                db_path=DB_PATH,
                run_id=self.run_id,
            )

            # Single git runner for diff queries across all roles
            self._git_runner = OpenCodeAgentRunner(
                worktree_path=str(wt_path),
                role="orchestrator",
            )

            task = feature_request
            iteration = 0
            done = False
            result = None

            while not done and iteration < self.max_iterations:
                plan = await self._execute_role("planner", task, context, "plan")
                if self._needs_human(plan):
                    plan = await self._wait_for_human(plan)

                code = await self._execute_role("coder", json.dumps(plan), context, "code")
                if self._needs_human(code):
                    code = await self._wait_for_human(code)

                test = await self._execute_role("tester", json.dumps(code), context, "test")
                if self._needs_human(test):
                    test = await self._wait_for_human(test)

                eval_input = json.dumps({"plan": plan, "code": code, "test": test})
                eval_result = await self._execute_role("planner", eval_input, context, "evaluate")
                if self._needs_human(eval_result):
                    eval_result = await self._wait_for_human(eval_result)

                done = (eval_result.get("action") == "done")
                task = eval_result.get("next_task", task)
                result = eval_result

                iteration += 1
                await self._update_iterations(iteration)

            if done:
                await self._update_status("done")
                await self._broadcast({
                    "type": "done",
                    "status": "done",
                    "summary": "All phases complete",
                    "roadmap": result,
                })
                return result
            else:
                await self._update_status("failed")
                await self._broadcast({
                    "type": "failed",
                    "status": "failed",
                    "message": "Max iterations reached without completing all phases",
                })
                return result

        except OpenCodeAgentError as e:
            await self._update_status("failed")
            await self._broadcast({"type": "failed", "status": "failed", "message": str(e)})
            raise
        except Exception as e:
            await self._update_status("failed")
            await self._broadcast({"type": "error", "phase": "unknown", "message": str(e), "retryable": False})
            raise
        finally:
            # Cleanup worktree
            if self._worktree_manager:
                self._worktree_manager.remove()

    async def _execute_role(self, role: str, task: str, context: dict, step_type: str) -> dict:
        """Execute a single role step in the sequential pipeline."""
        start = time.time()
        self._step_number += 1
        step_number = self._step_number

        # 1. Resolve agent
        agent = self._role_resolver.assign(role)

        # 2. Build system prompt
        system_prompt = self._build_system_prompt(agent)

        # 3. Run OpenCodeAgentRunner per step
        runner = OpenCodeAgentRunner(
            worktree_path=str(self._worktree_manager.worktree_path),
            role=role,
            model=agent.get("model_name"),
        )

        phase_name = f"{step_type}_{role}"
        await self._update_status(phase_name)

        try:
            result = runner.run(task, system_prompt=system_prompt)
        except OpenCodeAgentError as e:
            latency_ms = int((time.time() - start) * 1000)
            error_msg = str(e)
            await self._session_logger.log_step(
                step_number=step_number,
                role=role,
                step_type=step_type,
                input_data=task,
                output_data=None,
                latency_ms=latency_ms,
                error=error_msg,
                files_changed=None,
                git_commit=None,
            )
            await self._broadcast({
                "type": "phase_error",
                "phase": phase_name,
                "message": error_msg,
                "retryable": True,
            })
            raise

        latency_ms = int((time.time() - start) * 1000)

        # Parse structured output
        output = result.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = {"raw_output": output, "files_changed": result.get("files_changed", [])}
        elif output is None:
            output = {"raw_output": result.get("raw_output", ""), "files_changed": result.get("files_changed", [])}

        # 5. Commit changes if files changed
        files_changed = result.get("files_changed", [])
        git_commit = None
        if files_changed:
            try:
                committed = self._worktree_manager.commit(
                    f"run-{self.run_id}: {role} {step_type}",
                    files=files_changed,
                )
                if committed:
                    commit_result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=str(self._worktree_manager.worktree_path),
                        capture_output=True,
                        text=True,
                    )
                    git_commit = commit_result.stdout.strip() if commit_result.returncode == 0 else None
            except Exception:
                pass

        # 4. Log step via SessionLogger
        await self._session_logger.log_step(
            step_number=step_number,
            role=role,
            step_type=step_type,
            input_data=task,
            output_data=json.dumps(output),
            latency_ms=latency_ms,
            error=None,
            files_changed=files_changed,
            git_commit=git_commit,
        )

        # 6. Broadcast WebSocket events
        await self._broadcast({
            "type": "agent_output",
            "phase": phase_name,
            "agent": role,
            "output": output,
            "error": None,
        })

        # 7. Handle human escalation
        if self._needs_human(output):
            output = await self._wait_for_human(output)

        return output

    def _build_system_prompt(self, agent: dict) -> str:
        """Assemble system prompt from base prompt, DoD, CHANGELOG, and git diff."""
        parts = []
        base = agent.get("system_prompt", "")
        if base:
            parts.append(base)

        if self.definition_of_done:
            parts.append(f"Definition of Done:\n{self.definition_of_done}")

        try:
            changelog = self._worktree_manager.read_file("CHANGELOG.md")
            if changelog and not changelog.startswith("File "):
                parts.append(f"Changelog:\n{changelog}")
        except Exception:
            pass

        try:
            if self._git_runner and self._base_commit:
                diff = self._git_runner.get_git_diff(self._base_commit)
                if diff:
                    parts.append(f"Git Diff:\n{diff}")
        except Exception:
            pass

        return "\n\n".join(parts)

    async def _load_agents(self) -> dict:
        """Fetch all agents for this job from the DB."""
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        agents = {}
        mapping = {
            "planner_agent_id": "planner",
            "coder_agent_id": "coder",
            "tester_agent_id": "tester",
        }
        for col, role in mapping.items():
            row = await (await db.execute(
                f"SELECT a.* FROM agents a JOIN jobs j ON a.id = j.{col} WHERE j.id = ?",
                (self.job["id"],)
            )).fetchone()
            if row:
                agents[row["id"]] = dict(row)
        await db.close()
        return agents

    async def _update_status(self, status: str):
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE runs SET status = ?, completed_at = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat() if status in ("done", "failed") else None, self.run_id)
        )
        await db.commit()
        await db.close()
        await ws_manager.send(self.run_id, {"type": "phase_change", "phase": status, "message": f"Entering {status}", "timestamp": datetime.now(timezone.utc).isoformat()})

    async def _broadcast(self, event: dict):
        await ws_manager.send(self.run_id, event)

    def _needs_human(self, output: dict) -> bool:
        if not output or not isinstance(output, dict):
            return False
        req = output.get("human_input_request")
        if req is None:
            return False
        if isinstance(req, str):
            return bool(req.strip())
        return isinstance(req, dict) and bool(req.get("message", "").strip())

    async def _wait_for_human(self, output: dict):
        req = output["human_input_request"]
        if isinstance(req, str):
            req = {"requested_by": "agent", "message": req, "input_type": "text"}

        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        prev_status_row = await (await db.execute("SELECT status FROM runs WHERE id = ?", (self.run_id,))).fetchone()
        prev_status = prev_status_row["status"] if prev_status_row else "planning_draft"
        await db.execute("UPDATE runs SET status = 'waiting_for_human' WHERE id = ?", (self.run_id,))
        await db.commit()
        await db.close()

        await ws_manager.send(self.run_id, {
            "type": "human_input_required",
            "requested_by": req.get("requested_by", "agent"),
            "message": req.get("message", ""),
            "input_type": req.get("input_type", "text")
        })

        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        requests = json.loads((await (await db.execute("SELECT human_requests FROM runs WHERE id = ?", (self.run_id,))).fetchone())["human_requests"] or "[]")
        request_entry = {"request": req, "response": None, "previous_status": prev_status, "timestamp": datetime.now(timezone.utc).isoformat()}
        requests.append(request_entry)
        await db.execute("UPDATE runs SET human_requests = ? WHERE id = ?", (json.dumps(requests), self.run_id))
        await db.commit()
        await db.close()

        event = ws_manager.get_human_input_event(self.run_id)
        try:
            await asyncio.wait_for(event.wait(), timeout=3600)
        except asyncio.TimeoutError:
            raise Exception("Human input timed out after 1 hour")
        finally:
            ws_manager.clear_human_input_event(self.run_id)

        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        requests = json.loads((await (await db.execute("SELECT human_requests FROM runs WHERE id = ?", (self.run_id,))).fetchone())["human_requests"] or "[]")
        await db.close()

        output["_human_response"] = requests[-1]["response"]
        return output

    async def _get_setting(self, key: str) -> str:
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT value FROM settings WHERE key = ?", (key,))).fetchone()
        await db.close()
        return row["value"] if row else ""

    async def _save_roadmap(self, plan: dict):
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute("UPDATE runs SET roadmap = ? WHERE id = ?", (json.dumps(plan), self.run_id))
        await db.commit()
        await db.close()

    async def _update_iterations(self, count: int):
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute("UPDATE runs SET iterations = ? WHERE id = ?", (count, self.run_id))
        await db.commit()
        await db.close()

    async def _write_files(self, coder_output: dict):
        working_dir = await self._get_setting("working_dir")
        if not working_dir:
            return
        for f in coder_output.get("patch_or_full_files", []):
            path = f["path"]
            full_path = os.path.join(working_dir, path)
            if not os.path.realpath(full_path).startswith(os.path.realpath(working_dir)):
                raise ValueError(f"Path escape attempt: {path}")
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as fh:
                fh.write(f["content"])
