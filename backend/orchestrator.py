import json
import os
import subprocess
import asyncio
from datetime import datetime
from database import DB_PATH
from websocket import ws_manager
from ollama_client import call_ollama, OllamaError
import aiosqlite

class Orchestrator:
    def __init__(self, run_id: int, job_config: dict):
        self.run_id = run_id
        self.job = job_config
        self.overrides = json.loads(job_config.get("agent_overrides", "{}"))
        self.max_iterations = job_config.get("max_iterations", 5)

    async def run(self, feature_request: str, context: dict):
        try:
            await self._update_status("planning_draft")
            roadmap = await self._planning_phase(feature_request, context)
            if not self._needs_human(roadmap):
                await self._update_status("planning_finalize")
                result = await self._execution_loop(roadmap)
            else:
                result = roadmap

            await self._update_status("done")
            await self._broadcast({"type": "done", "status": "done", "summary": "All phases complete", "roadmap": result})
            return result
        except OllamaError as e:
            await self._update_status("failed")
            await self._broadcast({"type": "failed", "status": "failed", "message": str(e)})
            raise
        except Exception as e:
            await self._update_status("failed")
            await self._broadcast({"type": "error", "phase": "unknown", "message": str(e), "retryable": False})
            raise

    async def _planning_phase(self, feature_request: str, context: dict):
        planner = await self._get_agent("planner")
        working_dir = await self._get_setting("working_dir")
        files_content = self._read_context_files(context.get("selected_files", []), working_dir)

        draft = await self._call_agent(planner, {
            "role": "system", "content": planner["system_prompt"]
        }, {
            "role": "user",
            "content": f"Feature request:\n{feature_request}\n\nContext files:\n{files_content}\n\nKnown bugs: {context.get('known_bugs', [])}\nConstraints: {context.get('constraints', [])}\nExtra notes: {context.get('extra_notes', '')}\n\nProduce a phased roadmap with definition_of_done per phase."
        })
        await self._broadcast({"type": "agent_output", "phase": "planning_draft", "agent": "planner", "output": draft})

        if self._needs_human(draft):
            return draft

        await self._update_status("planning_review_coder")
        coder = await self._get_agent("coder")
        coder_review = await self._call_agent(coder, {
            "role": "system",
            "content": "You are reviewing a development plan as the coder. Identify technical issues, infeasible tasks, or better approaches. Return JSON: {verdict, concerns, technical_suggestions, human_input_request}"
        }, {
            "role": "user",
            "content": f"Review this plan:\n{json.dumps(draft, indent=2)}"
        })
        await self._broadcast({"type": "agent_output", "phase": "planning_review_coder", "agent": "coder", "output": coder_review})

        await self._update_status("planning_review_tester")
        tester = await self._get_agent("tester")
        tester_review = await self._call_agent(tester, {
            "role": "system",
            "content": "You are reviewing a development plan as the tester. Identify missing edge cases, test gaps, or automation concerns. Return JSON: {verdict, missing_test_scenarios, test_approach_suggestions, human_input_request}"
        }, {
            "role": "user",
            "content": f"Review this plan:\n{json.dumps(draft, indent=2)}"
        })
        await self._broadcast({"type": "agent_output", "phase": "planning_review_tester", "agent": "tester", "output": tester_review})

        await self._update_status("planning_finalize")
        feedback = f"Coder concerns: {json.dumps(coder_review.get('concerns', []))}\nCoder suggestions: {json.dumps(coder_review.get('technical_suggestions', []))}\nTester missing scenarios: {json.dumps(tester_review.get('missing_test_scenarios', []))}\nTester suggestions: {json.dumps(tester_review.get('test_approach_suggestions', []))}"

        final_plan = await self._call_agent(planner, {
            "role": "system", "content": planner["system_prompt"]
        }, {
            "role": "user",
            "content": f"Your original plan:\n{json.dumps(draft, indent=2)}\n\nReview feedback:\n{feedback}\n\nIncorporate the feedback and return the finalized roadmap."
        })
        await self._broadcast({"type": "agent_output", "phase": "planning_finalize", "agent": "planner", "output": final_plan})
        await self._save_roadmap(final_plan)
        return final_plan

    async def _execution_loop(self, roadmap):
        phases = roadmap.get("roadmap", [])
        phase_idx = 0
        iteration = 0

        while iteration < self.max_iterations and phase_idx < len(phases):
            current = phases[phase_idx]
            await self._update_status("coding")

            coder = await self._get_agent("coder")
            coder_output = await self._call_agent(coder, {
                "role": "system", "content": coder["system_prompt"]
            }, {
                "role": "user",
                "content": f"Implement this phase:\n{json.dumps(current, indent=2)}\n\nDefinition of Done for coder: {current.get('definition_of_done', {}).get('for_coder', '')}"
            })
            await self._broadcast({"type": "agent_output", "phase": "coding", "agent": "coder", "output": coder_output})
            await self._append_output("coder_outputs", coder_output)
            self._write_files(coder_output)

            if self._needs_human(coder_output):
                coder_output = await self._wait_for_human(coder_output)
                await self._append_output("coder_outputs", coder_output)

            await self._update_status("testing")
            working_dir = await self._get_setting("working_dir")
            lint_result = self._run_command("ruff check ." if working_dir else "echo 'no lint configured'")
            test_result = self._run_command("pytest -q" if working_dir else "echo 'no tests configured'")

            tester = await self._get_agent("tester")
            tester_output = await self._call_agent(tester, {
                "role": "system", "content": tester["system_prompt"]
            }, {
                "role": "user",
                "content": f"Phase:\n{json.dumps(current, indent=2)}\n\nCoder output:\n{json.dumps(coder_output, indent=2)}\n\nLint:\n{json.dumps(lint_result)}\n\nTests:\n{json.dumps(test_result)}\n\nDoD for coder: {current.get('definition_of_done', {}).get('for_coder', '')}\nDoD for tester: {current.get('definition_of_done', {}).get('for_tester', '')}"
            })
            await self._broadcast({"type": "agent_output", "phase": "testing", "agent": "tester", "output": tester_output})
            await self._append_output("test_reports", tester_output)

            if self._needs_human(tester_output):
                tester_output = await self._wait_for_human(tester_output)

            await self._update_status("evaluating")
            planner = await self._get_agent("planner")
            decision = await self._call_agent(planner, {
                "role": "system",
                "content": "You are re-evaluating the plan after an execution iteration. Return JSON: {action: 'continue'|'adjust'|'done', reasoning, revised_roadmap, next_tasks_for_coder, human_input_request}"
            }, {
                "role": "user",
                "content": f"Roadmap:\n{json.dumps(roadmap, indent=2)}\n\nCurrent phase ({phase_idx + 1}/{len(phases)}):\n{json.dumps(current, indent=2)}\n\nCoder output:\n{json.dumps(coder_output, indent=2)}\n\nTest report:\n{json.dumps(tester_output, indent=2)}"
            })
            await self._broadcast({"type": "agent_output", "phase": "evaluating", "agent": "planner", "output": decision})

            if decision.get("action") == "done":
                break
            elif decision.get("action") == "adjust" and decision.get("revised_roadmap"):
                roadmap = decision["revised_roadmap"]
                phases = roadmap.get("roadmap", [])
            elif decision.get("action") == "continue":
                phase_idx += 1

            iteration += 1

        return roadmap

    async def _call_agent(self, agent_config: dict, system_msg: dict, user_msg: dict) -> dict:
        endpoint = agent_config.get("ollama_endpoint", "http://localhost:11434")
        model = agent_config.get("model_name")
        temp = agent_config.get("temperature", 0.3)

        override = self.overrides.get(agent_config.get("_role", ""), {})
        if override.get("temperature") is not None:
            temp = override["temperature"]

        system_content = agent_config["system_prompt"]
        if override.get("system_prompt_append"):
            system_content += "\n\n" + override["system_prompt_append"]

        messages = [
            {"role": "system", "content": system_content},
            user_msg
        ]
        return await call_ollama(endpoint, model, messages, temp)

    async def _get_agent(self, role: str) -> dict:
        db = await aiosqlite.connect(DB_PATH)
        col = f"{role}_agent_id"
        row = await (await db.execute(
            "SELECT a.* FROM agents a JOIN jobs j ON a.id = j." + col + " WHERE j.id = ?",
            (self.job["id"],)
        )).fetchone()
        await db.close()
        result = dict(row)
        result["_role"] = role
        return result

    async def _update_status(self, status: str):
        db = await aiosqlite.connect(DB_PATH)
        await db.execute(
            "UPDATE runs SET status = ?, completed_at = ? WHERE id = ?",
            (status, datetime.utcnow().isoformat() if status in ("done", "failed") else None, self.run_id)
        )
        await db.commit()
        await db.close()
        await ws_manager.send(self.run_id, {"type": "phase_change", "phase": status, "message": f"Entering {status}", "timestamp": datetime.utcnow().isoformat()})

    async def _broadcast(self, event: dict):
        await ws_manager.send(self.run_id, event)

    def _needs_human(self, output: dict) -> bool:
        return output.get("human_input_request") is not None

    async def _wait_for_human(self, output: dict):
        req = output["human_input_request"]

        db = await aiosqlite.connect(DB_PATH)
        await db.execute("UPDATE runs SET status = 'waiting_for_human' WHERE id = ?", (self.run_id,))
        await db.commit()
        await db.close()

        await ws_manager.send(self.run_id, {
            "type": "human_input_required",
            "requested_by": req["requested_by"],
            "message": req["message"],
            "input_type": req.get("input_type", "text")
        })

        db = await aiosqlite.connect(DB_PATH)
        requests = json.loads((await (await db.execute("SELECT human_requests FROM runs WHERE id = ?", (self.run_id,))).fetchone())["human_requests"] or "[]")
        request_entry = {"request": req, "response": None, "timestamp": datetime.utcnow().isoformat()}
        requests.append(request_entry)
        await db.execute("UPDATE runs SET human_requests = ? WHERE id = ?", (json.dumps(requests), self.run_id))
        await db.commit()
        await db.close()

        while True:
            await asyncio.sleep(1)
            db = await aiosqlite.connect(DB_PATH)
            status_row = await (await db.execute("SELECT status, human_requests FROM runs WHERE id = ?", (self.run_id,))).fetchone()
            requests = json.loads(status_row["human_requests"] or "[]")
            await db.close()
            if status_row["status"] != "waiting_for_human" and requests and requests[-1].get("response"):
                break

        output["_human_response"] = requests[-1]["response"]
        return output

    def _write_files(self, coder_output: dict):
        import asyncio as asyncio_mod
        working_dir = asyncio_mod.run(self._get_setting("working_dir"))
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
        row = await (await db.execute("SELECT value FROM settings WHERE key = ?", (key,))).fetchone()
        await db.close()
        return row["value"] if row else ""

    async def _save_roadmap(self, plan: dict):
        db = await aiosqlite.connect(DB_PATH)
        await db.execute("UPDATE runs SET roadmap = ? WHERE id = ?", (json.dumps(plan), self.run_id))
        await db.commit()
        await db.close()

    async def _append_output(self, field: str, output: dict):
        db = await aiosqlite.connect(DB_PATH)
        row = await (await db.execute(f"SELECT {field} FROM runs WHERE id = ?", (self.run_id,))).fetchone()
        items = json.loads(row[field] or "[]")
        items.append(output)
        await db.execute(f"UPDATE runs SET {field} = ? WHERE id = ?", (json.dumps(items), self.run_id))
        await db.commit()
        await db.close()
