import json
import os
import subprocess
import asyncio
import time
from datetime import datetime, timezone
from database import DB_PATH
from websocket import ws_manager
from claude_agent import ClaudeAgentRunner, ClaudeAgentError
from worktree_manager import WorktreeManager
import aiosqlite

class Orchestrator:
    def __init__(self, run_id: int, job_config: dict):
        self.run_id = run_id
        self.job = job_config
        self.overrides = json.loads(job_config.get("agent_overrides", "{}"))
        self.max_iterations = job_config.get("max_iterations", 5)
        self._phase_retry_count = {}
        self._worktree_manager = None
        self._agents = {}

    async def run(self, feature_request: str, context: dict):
        try:
            # Verify Claude Code CLI is available
            import shutil
            if not shutil.which("claude"):
                raise RuntimeError(
                    "Claude Code CLI not found. Install it first: npm install -g @anthropic-ai/claude-code"
                )

            # Initialize worktrees for each agent
            working_dir = await self._get_setting("working_dir") or "."
            self._worktree_manager = WorktreeManager(working_dir, self.run_id)

            # Create worktrees and agent runners
            for role in ["planner", "coder", "tester"]:
                wt_path = self._worktree_manager.create_worktree(role)
                self._agents[role] = ClaudeAgentRunner(
                    worktree_path=str(wt_path),
                    role=role,
                    allowed_tools=["Bash", "Read", "Edit", "Write", "Agent"],
                    max_budget_usd=5.0,
                )

            await self._update_status("planning_draft")
            roadmap = await self._planning_phase(feature_request, context)

            if self._needs_human(roadmap):
                roadmap = await self._wait_for_human(roadmap)
                human_response = roadmap.get("_human_response", "")
                await self._update_status("planning_draft")
                roadmap = await self._planning_phase(feature_request, context, human_response)

            if not self._needs_human(roadmap):
                await self._update_status("planning_finalize")
                exec_result = await self._execution_loop(roadmap)
                if not exec_result["completed"]:
                    await self._update_status("failed")
                    await self._broadcast({"type": "failed", "status": "failed", "message": "Max iterations reached without completing all phases"})
                    return exec_result["roadmap"]
                result = exec_result["roadmap"]
            else:
                result = roadmap

            await self._update_status("done")
            await self._broadcast({"type": "done", "status": "done", "summary": "All phases complete", "roadmap": result})
            return result
        except ClaudeAgentError as e:
            await self._update_status("failed")
            await self._broadcast({"type": "failed", "status": "failed", "message": str(e)})
            raise
        except Exception as e:
            await self._update_status("failed")
            await self._broadcast({"type": "error", "phase": "unknown", "message": str(e), "retryable": False})
            raise
        finally:
            # Cleanup worktrees
            if self._worktree_manager:
                self._worktree_manager.cleanup_all()

    async def _planning_phase(self, feature_request: str, context: dict, human_response: str = ""):
        planner = await self._get_agent("planner")
        working_dir = await self._get_setting("working_dir")
        files_content = self._read_context_files(context.get("selected_files", []), working_dir)

        human_context = f"\n\nHuman response from previous request: {human_response}" if human_response else ""

        system_prompt = planner["system_prompt"]
        user_prompt = f"""Feature request:
{feature_request}

Context files:
{files_content}

Known bugs: {context.get('known_bugs', [])}
Constraints: {context.get('constraints', [])}
Extra notes: {context.get('extra_notes', '')}{human_context}

Produce a phased roadmap with definition_of_done per phase. Return JSON with: goal, tasks, files_needed, risks, acceptance_criteria, test_plan, roadmap (list of phases)."""

        draft, draft_error = await self._call_claude_agent_with_retry(
            "planner", system_prompt, user_prompt, phase="planning_draft"
        )
        await self._broadcast({"type": "agent_output", "phase": "planning_draft", "agent": "planner", "output": draft, "error": draft_error})

        if draft_error or self._needs_human(draft):
            return draft if draft else {"error": draft_error}

        await self._update_status("planning_review_coder")
        await self._update_status("planning_review_tester")

        # Run coder and tester reviews IN PARALLEL
        coder_review_task = self._call_claude_agent_with_retry(
            "coder",
            "You are reviewing a development plan as the coder. Identify technical issues, infeasible tasks, or better approaches. Return JSON: {verdict, concerns, technical_suggestions, human_input_request}",
            f"Review this plan:\n{json.dumps(draft, indent=2)}",
            phase="planning_review_coder"
        )
        tester_review_task = self._call_claude_agent_with_retry(
            "tester",
            "You are reviewing a development plan as the tester. Identify missing edge cases, test gaps, or automation concerns. Return JSON: {verdict, missing_test_scenarios, test_approach_suggestions, human_input_request}",
            f"Review this plan:\n{json.dumps(draft, indent=2)}",
            phase="planning_review_tester"
        )

        (coder_review, coder_error), (tester_review, tester_error) = await asyncio.gather(
            coder_review_task, tester_review_task
        )

        await self._broadcast({"type": "agent_output", "phase": "planning_review_coder", "agent": "coder", "output": coder_review, "error": coder_error})
        await self._broadcast({"type": "agent_output", "phase": "planning_review_tester", "agent": "tester", "output": tester_review, "error": tester_error})

        await self._update_status("planning_finalize")
        feedback = f"Coder concerns: {json.dumps(coder_review.get('concerns', []) if coder_review else [])}\nCoder suggestions: {json.dumps(coder_review.get('technical_suggestions', []) if coder_review else [])}\nTester missing scenarios: {json.dumps(tester_review.get('missing_test_scenarios', []) if tester_review else [])}\nTester suggestions: {json.dumps(tester_review.get('test_approach_suggestions', []) if tester_review else [])}"

        final_plan, final_error = await self._call_claude_agent_with_retry(
            "planner",
            system_prompt,
            f"Your original plan:\n{json.dumps(draft, indent=2)}\n\nReview feedback:\n{feedback}\n\nIncorporate the feedback and return the finalized roadmap.",
            phase="planning_finalize"
        )
        await self._broadcast({"type": "agent_output", "phase": "planning_finalize", "agent": "planner", "output": final_plan, "error": final_error})
        await self._save_roadmap(final_plan)

        # Commit planner output to worktree
        if self._worktree_manager:
            try:
                plan_json = json.dumps(final_plan, indent=2)
                self._worktree_manager.write_file("planner", "plan.json", plan_json)
                self._worktree_manager.commit("planner", f"run-{self.run_id}: finalize plan")
            except Exception:
                pass

        return final_plan

    async def _execution_loop(self, roadmap):
        phases = roadmap.get("roadmap", [])
        phase_idx = 0
        iteration = 0

        while iteration < self.max_iterations and phase_idx < len(phases):
            current = phases[phase_idx]
            await self._update_status("coding")

            coder = await self._get_agent("coder")
            coder_system = coder["system_prompt"]
            coder_user = f"Implement this phase:\n{json.dumps(current, indent=2)}\n\nDefinition of Done for coder: {current.get('definition_of_done', {}).get('for_coder', '')}"

            coder_output, coder_error = await self._call_claude_agent_with_retry(
                "coder", coder_system, coder_user, phase="coding"
            )
            await self._broadcast({"type": "agent_output", "phase": "coding", "agent": "coder", "output": coder_output, "error": coder_error})

            if coder_output:
                await self._append_output("coder_outputs", coder_output)
                await self._write_files(coder_output)
                # Commit coder changes
                if self._worktree_manager:
                    try:
                        self._worktree_manager.commit("coder", f"run-{self.run_id}: phase {phase_idx + 1} coding")
                    except Exception:
                        pass

            if self._needs_human(coder_output):
                coder_output = await self._wait_for_human(coder_output)
                await self._append_output("coder_outputs", coder_output)

            await self._update_status("testing")
            working_dir = await self._get_setting("working_dir")
            lint_result = self._run_command("ruff check ." if working_dir else "echo 'no lint configured'")
            test_result = self._run_command("pytest -q" if working_dir else "echo 'no tests configured'")

            tester = await self._get_agent("tester")
            tester_system = tester["system_prompt"]
            tester_user = f"Phase:\n{json.dumps(current, indent=2)}\n\nCoder output:\n{json.dumps(coder_output, indent=2)}\n\nLint:\n{json.dumps(lint_result)}\n\nTests:\n{json.dumps(test_result)}\n\nDoD for coder: {current.get('definition_of_done', {}).get('for_coder', '')}\nDoD for tester: {current.get('definition_of_done', {}).get('for_tester', '')}"

            tester_output, tester_error = await self._call_claude_agent_with_retry(
                "tester", tester_system, tester_user, phase="testing"
            )
            await self._broadcast({"type": "agent_output", "phase": "testing", "agent": "tester", "output": tester_output, "error": tester_error})

            if tester_output:
                await self._append_output("test_reports", tester_output)
                # Commit tester report
                if self._worktree_manager:
                    try:
                        self._worktree_manager.write_file("tester", f"test_report_phase_{phase_idx}.json", json.dumps(tester_output, indent=2))
                        self._worktree_manager.commit("tester", f"run-{self.run_id}: phase {phase_idx + 1} testing")
                    except Exception:
                        pass

            if self._needs_human(tester_output):
                tester_output = await self._wait_for_human(tester_output)
                await self._append_output("test_reports", tester_output)

            await self._update_status("evaluating")
            planner = await self._get_agent("planner")
            planner_system = "You are re-evaluating the plan after an execution iteration. Return JSON: {action: 'continue'|'adjust'|'done', reasoning, revised_roadmap, next_tasks_for_coder, human_input_request}"
            planner_user = f"Roadmap:\n{json.dumps(roadmap, indent=2)}\n\nCurrent phase ({phase_idx + 1}/{len(phases)}):\n{json.dumps(current, indent=2)}\n\nCoder output:\n{json.dumps(coder_output, indent=2)}\n\nTest report:\n{json.dumps(tester_output, indent=2)}"

            decision, decision_error = await self._call_claude_agent_with_retry(
                "planner", planner_system, planner_user, phase="evaluating"
            )
            await self._broadcast({"type": "agent_output", "phase": "evaluating", "agent": "planner", "output": decision, "error": decision_error})

            if decision_error or not decision:
                await self._broadcast({"type": "phase_error", "phase": "evaluating", "message": decision_error or "Planner returned empty decision", "retryable": True})
                continue

            if decision.get("action") == "done":
                break
            elif decision.get("action") == "adjust" and decision.get("revised_roadmap"):
                roadmap = decision["revised_roadmap"]
                phases = roadmap.get("roadmap", [])
            elif decision.get("action") == "continue":
                phase_idx += 1

            iteration += 1
            await self._update_iterations(iteration)

        return {"roadmap": roadmap, "completed": phase_idx >= len(phases)}

    async def _call_claude_agent_with_retry(self, role: str, system_prompt: str, user_prompt: str, phase: str, max_retries: int = 1) -> tuple:
        """Call a Claude Code agent with per-phase retry logic. Returns (output, error)."""
        for attempt in range(max_retries + 1):
            start = time.time()
            try:
                agent = self._agents.get(role)
                if not agent:
                    raise ClaudeAgentError(f"No agent configured for role: {role}")

                result = agent.run(user_prompt, system_prompt=system_prompt)
                latency_ms = int((time.time() - start) * 1000)

                # Parse structured output from Claude Code
                output = result.get("output")
                if isinstance(output, str):
                    try:
                        output = json.loads(output)
                    except json.JSONDecodeError:
                        # If not valid JSON, wrap in a dict
                        output = {"raw_output": output, "files_changed": result.get("files_changed", [])}
                elif output is None:
                    output = {"raw_output": result.get("raw_output", ""), "files_changed": result.get("files_changed", [])}

                await self._save_step(phase, role, json.dumps({"system": system_prompt, "user": user_prompt}), json.dumps(output), latency_ms, None)
                return output, None
            except ClaudeAgentError as e:
                latency_ms = int((time.time() - start) * 1000)
                error_msg = str(e)
                await self._save_step(phase, role, json.dumps({"system": system_prompt, "user": user_prompt}), None, latency_ms, error_msg)
                if attempt == max_retries:
                    await self._broadcast({"type": "phase_error", "phase": phase, "message": error_msg, "retryable": True})
                    return None, error_msg
                await self._broadcast({"type": "phase_error", "phase": phase, "message": f"Attempt {attempt + 1} failed: {error_msg}. Retrying...", "retryable": True})
            except Exception as e:
                latency_ms = int((time.time() - start) * 1000)
                error_msg = str(e)
                await self._save_step(phase, role, json.dumps({"system": system_prompt, "user": user_prompt}), None, latency_ms, error_msg)
                await self._broadcast({"type": "phase_error", "phase": phase, "message": error_msg, "retryable": False})
                return None, error_msg
        return None, "Unexpected: all retries exhausted"

    async def _get_agent(self, role: str) -> dict:
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        allowed_cols = {"planner": "planner_agent_id", "coder": "coder_agent_id", "tester": "tester_agent_id"}
        col = allowed_cols.get(role)
        if not col:
            await db.close()
            raise ValueError(f"Invalid agent role: {role}")
        row = await (await db.execute(
            f"SELECT a.* FROM agents a JOIN jobs j ON a.id = j.{col} WHERE j.id = ?",
            (self.job["id"],)
        )).fetchone()
        await db.close()
        result = dict(row)
        result["_role"] = role
        return result

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

    def _read_context_files(self, paths: list, working_dir: str) -> str:
        if not paths or not working_dir:
            return "No files selected."
        contents = []
        for p in paths:
            full = os.path.join(working_dir, p)
            if os.path.isfile(full):
                with open(full) as f:
                    contents.append(f"--- {p} ---\n{f.read()}")
        return "\n\n".join(contents) if contents else "No readable files."

    def _run_command(self, cmd: str) -> dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=60)
            return {"command": cmd, "exit_code": result.returncode, "stdout": result.stdout[:5000], "stderr": result.stderr[:5000]}
        except Exception as e:
            return {"command": cmd, "exit_code": -1, "stdout": "", "stderr": str(e)}

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

    async def _append_output(self, field: str, output: dict):
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(f"SELECT {field} FROM runs WHERE id = ?", (self.run_id,))).fetchone()
        items = json.loads(row[field] or "[]")
        items.append(output)
        await db.execute(f"UPDATE runs SET {field} = ? WHERE id = ?", (json.dumps(items), self.run_id))
        await db.commit()
        await db.close()

    async def _save_step(self, phase: str, agent: str, input_data: str, output_data: str | None, latency_ms: int, error: str | None):
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO run_steps (run_id, phase, agent, input, output, latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.run_id, phase, agent, input_data, output_data, latency_ms, error)
        )
        await db.commit()
        await db.close()
