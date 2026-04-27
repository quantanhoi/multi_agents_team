# Multi-Agent LLM Orchestration System — Design Spec

## Overview

A system that coordinates 3 LLM agents (Planner, Coder, Tester) running on Ollama Cloud to collaboratively build software. A React UI lets users configure agents and jobs, trigger runs, and review results. A Python FastAPI backend runs the orchestration loop.

**Models:** Kimi K2.6 (Planner), GLM-5.1 (Coder), DeepSeek-V4-Pro (Tester) — all configurable.

---

## Architecture

Monolithic FastAPI backend + React SPA frontend + SQLite persistence.

```
React SPA  ←→  FastAPI Backend  ←→  Ollama Cloud API
(Browser)      (REST + WebSocket)    SQLite DB
                                    Working Directory (state/ + artifacts/)
```

- **Frontend:** React SPA with sidebar navigation, 5 pages
- **Backend:** FastAPI serving REST API + WebSocket for per-run phase updates
- **Orchestrator:** Async Python class instantiated per-run, runs the full lifecycle
- **Persistence:** SQLite — agents, jobs, runs all queryable

---

## Orchestration Loop

### Phase 1: Planning & Review

1. **Planner drafts roadmap** — receives feature request + repo context + files, produces phased roadmap with definition-of-done per phase
2. **Coder reviews plan** — flags infeasible tasks, suggests technical alternatives
3. **Tester reviews plan** — flags missing test scenarios, edge cases, test strategy gaps
4. **Planner finalizes** — incorporates feedback, locks roadmap, execution begins

### Phase 2: Execution Loop

```
Coder → Tester → Planner (re-evaluate) → continue/adjust/done
```

- **Coder** implements current phase tasks against for_coder DoD
- **Tester** runs automated checks (lint + pytest via orchestrator, not model) + reviews code, verifies both DoDs
- **Planner** reviews test results + current state, decides:
  - **Continue:** phase complete, advance to next
  - **Adjust:** update roadmap based on learnings
  - **Done:** all phases complete, acceptance criteria met

### Human Input Mechanism

Any agent can include an optional `human_input_request` in their JSON output. When triggered:
1. Orchestrator pauses, WS emits `human_input_required` with request details
2. UI shows notification with the request (text, screenshot upload, etc.)
3. User provides input and clicks Resume
4. Orchestrator passes response back to requesting agent, loop continues

`waiting_for_human` can interrupt any phase.

### Run Lifecycle States

The `status` field on a run is the single source of truth for where the run is. Valid states:

```
pending → planning_draft → planning_review_coder → planning_review_tester
→ planning_finalize → coding → testing → evaluating → (loop back to coding or advance)
→ waiting_for_human (set when any agent requests human input; previous state preserved)
→ done / failed
```

When a run enters `waiting_for_human`, its pre-pause state is preserved so the orchestrator knows where to resume.

---

## Data Model

### SQLite Tables

**agents:** id, name, role (planner|coder|tester), model_name, system_prompt, temperature (default 0.3), ollama_endpoint, created_at, updated_at

**jobs:** id, name, description, planner_agent_id (FK), coder_agent_id (FK), tester_agent_id (FK), agent_overrides (JSON), loop_mode (automatic|manual), max_iterations (default 5), created_at, updated_at

**runs:** id, job_id (FK), status (one of the lifecycle states), feature_request (text), context (JSON, see below), iterations (int), roadmap (JSON), coder_outputs (JSON array), test_reports (JSON array), human_requests (JSON array — each entry is the agent's request + the user's response), started_at, completed_at

**settings:** key (text, PK), value (text) — simple key-value store. Keys: `working_dir`, `ollama_endpoint`, `default_temperature`.

**Run context JSON shape:**
```json
{
  "selected_files": ["path/to/file.py", "path/to/another.py"],
  "known_bugs": ["bug description or issue link"],
  "constraints": ["must use bcrypt", "keep API backward-compatible"],
  "extra_notes": "any additional context for the planner"
}
```

**Job agent_overrides shape:**
```json
{
  "planner": {"model_name": "optional override", "temperature": 0.2, "system_prompt_append": "extra instructions"},
  "coder": {"model_name": null, "temperature": null, "system_prompt_append": null},
  "tester": {"model_name": null, "temperature": null, "system_prompt_append": null}
}
```

Override fields are nullable — null means "use the agent preset value as-is."

### Agent JSON Output Schemas

**Planner:**
```json
{
  "goal": "...",
  "roadmap": [{
    "phase": 1,
    "name": "...",
    "tasks": ["..."],
    "definition_of_done": {
      "for_coder": "what coder must satisfy",
      "for_tester": "what tester must verify"
    }
  }],
  "files_needed": [],
  "risks": [],
  "human_input_request": null
}
```

**Coder:**
```json
{
  "summary": "...",
  "files_changed": [],
  "patch_or_full_files": [{"path": "...", "content": "..."}],
  "notes_for_tester": "...",
  "human_input_request": null
}
```

**Coder (review mode):**
```json
{
  "verdict": "approved|changes_requested",
  "concerns": [{"phase": N, "issue": "..."}],
  "technical_suggestions": [],
  "human_input_request": null
}
```

**Tester:**
```json
{
  "status": "pass|fail",
  "bugs": [{"severity": "high|medium|low", "description": "...", "file": "..."}],
  "definition_of_done_check": {
    "for_coder": "PASS|FAIL - notes",
    "for_tester": "PASS|FAIL - notes"
  },
  "manual_test_checklist": [],
  "automation_gaps": [],
  "next_action": "fix_bugs|continue|done",
  "human_input_request": null
}
```

**Tester (review mode):**
```json
{
  "verdict": "approved|changes_requested",
  "missing_test_scenarios": [],
  "test_approach_suggestions": [],
  "human_input_request": null
}
```

**Planner (re-evaluate):**
```json
{
  "action": "continue|adjust|done",
  "reasoning": "...",
  "revised_roadmap": null,
  "next_tasks_for_coder": [],
  "human_input_request": null
}
```

**human_input_request shape (agent → user):**
```json
{
  "message": "what the agent needs from the human",
  "input_type": "text|file_upload|screenshot_upload",
  "requested_by": "planner|coder|tester"
}
```

**Human response shape (user → agent, via POST /api/runs/:id/resume):**
```json
{
  "response_text": "user's answer or description",
  "uploaded_files": ["/path/to/screenshot.png"]
}
```

This response is attached to the `human_requests` array entry, then passed back to the requesting agent as a follow-up message in the next `_call_agent` invocation, so the agent can continue with the human's input.

---

## API Design

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/agents | List agent presets |
| POST | /api/agents | Create agent |
| GET | /api/agents/:id | Get agent |
| PUT | /api/agents/:id | Update agent |
| DELETE | /api/agents/:id | Delete agent |
| GET | /api/jobs | List jobs |
| POST | /api/jobs | Create job (agent assignments + overrides) |
| GET | /api/jobs/:id | Get job |
| PUT | /api/jobs/:id | Update job |
| DELETE | /api/jobs/:id | Delete job |
| POST | /api/runs | Start run (feature_request + context) |
| GET | /api/runs | Run history (filterable by job_id, status) |
| GET | /api/runs/:id | Full run details |
| POST | /api/runs/:id/resume | Resume paused run (submit human response) |
| POST | /api/runs/:id/stop | Stop running/paused run |
| GET | /api/settings | Get settings |
| PUT | /api/settings | Update settings |

### WebSocket — /ws/runs/:id

5 event types:

- `phase_change` — `{ phase, message, timestamp }`
- `agent_output` — `{ phase, agent, output: {...} }`
- `human_input_required` — `{ requested_by, message, input_type }`
- `done` / `failed` — `{ status, summary, roadmap }`
- `error` — `{ phase, message, retryable }`

---

## Frontend

### Layout

Sidebar nav (Agents, Jobs, Run, History, Settings) + top bar (system status: agent count, job count, working directory) + content area.

### Pages

1. **Agent Library** — grid of agent cards with role badge, model name, truncated prompt. Click to edit, + to create, delete with confirm.
2. **Jobs Manager** — list of jobs showing assigned agents + loop mode badge. Create/edit form: name, description, 3 agent dropdowns, per-agent overrides, loop mode toggle, max iterations.
3. **Run Console** — top: context builder (feature request textarea, file picker, bugs/constraints fields, Run button). Bottom: phase timeline pills, 3-panel output view (Plan | Coder Output | Test Report), human input prompt modal.
4. **History** — table of past runs (date, job, status, iterations, duration). Click to expand full detail.
5. **Settings** — working directory path, Ollama API base URL, default temperature.

### Phase Timeline

Horizontal pill trail: each lifecycle phase shown as a chip. Completed = green, active = blue with pulse, pending = outlined. Human-input pauses show a yellow `waiting_for_human` pill.

---

## Orchestrator Engine

```python
class Orchestrator:
    def __init__(self, run_id, job_config, ws_manager, db): ...

    async def run(self, feature_request, context) -> RunResult:
        # 1. Planning phase (4 sub-steps)
        roadmap = await self._planning_phase(feature_request, context)
        # 2. Execution loop
        result = await self._execution_loop(roadmap)
        # 3. Emit done/failed, return
        return result

    async def _planning_phase(self, ...) -> Roadmap: ...
    async def _execution_loop(self, roadmap) -> RunResult: ...
    async def _call_agent(self, agent, system_prompt, user_prompt) -> dict: ...
    async def _check_human_input(self, output) -> bool: ...
```

### Ollama Integration

POST to `{ollama_endpoint}/api/chat`:
```json
{
  "model": "glm-5.1",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "format": "json",
  "stream": false,
  "options": {"temperature": 0.3}
}
```

- Parse `response["message"]["content"]` as JSON
- Retry up to 2 times on network errors
- JSON parse failures → wrap error, feed back to agent for retry (not counted as iteration)

### File Safety

- All file writes go through the orchestrator, never raw model output
- Coder's `patch_or_full_files` is validated before writing (paths must be within working directory)
- Orchestrator runs lint + pytest itself, tester model only reviews the output

### Working Directory Integration

The orchestrator reads from the configured working directory at the start of each phase:
- `{working_dir}/state/context.md` — project summary, updated by orchestrator after each iteration
- `{working_dir}/state/plan.json` — planner's output, written after planning finalize
- `{working_dir}/artifacts/` — lint output, test output, written by orchestrator before tester is called

The context builder in the UI lets the user browse and select files from the working directory to include as `context.selected_files`. The orchestrator reads those files and includes their contents in the planner's user prompt.

---

## Manual Gates Mode (Future)

Same `waiting_for_human` mechanism, triggered at predefined checkpoints:
- After planner draft → user approves before review round
- After planner finalize → user approves before first code
- After each iteration → user decides next action

Configurable per job: which gates are active.

---

## Error Handling

- **Ollama API errors:** retry up to 2x, then mark run as `failed` with error details
- **JSON parse failures:** feed error back to same agent for correction (one retry), then fail
- **File write safety:** validate all paths are within working directory, reject runs that try to write outside
- **Run stop:** user can stop any run, orchestrator cancels current agent call and cleans up
- **WebSocket disconnect:** run continues server-side, client reconnects and gets current state

---

## Scope

### v1 (this implementation)
- Agent CRUD (library)
- Job CRUD (agent assignment + overrides)
- Run: context builder + trigger
- Full automatic loop (planning review + execution)
- Human input mechanism
- Run console with phase timeline + output panels
- Run history + detail view
- Settings (working directory, Ollama endpoint)

### Out of scope for v1
- Manual gates mode (designed for, not built)
- Multiple concurrent runs
- Scheduled/recurring jobs
- Authentication / multi-user
