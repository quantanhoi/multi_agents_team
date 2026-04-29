# Session Changelog — 2026-04-29

This document captures the refactor from parallel-review/sequential-execution to a **strictly sequential, role-based pipeline** with dynamic assignment.

---

## 1. Backend Refactor — Sequential Pipeline

### `backend/opencode_agent.py` (new file)

**Replaces:** `backend/claude_agent.py` (deleted)

| Change | Details |
|--------|---------|
| CLI command | `claude` → `opencode run` |
| Model flag | Added `--model <model>` for per-step model assignment |
| Unsupported flags removed | `--bare`, `--allowed-tools`, `--output-format`, `--max-budget-usd` (not supported by opencode) |
| New methods | `get_git_diff(since_ref)`, `read_git_history(n=5)` |
| Backwards compat | `read_history` alias for `read_git_history` |

### `backend/worktree_manager.py`

| Change | Details |
|--------|---------|
| From 3 worktrees per run | To **1 shared worktree** per run |
| Worktree path | `run-{id}` (no role suffix) |
| Branch name | `agent/run-{id}` (no role suffix) |
| API change | Removed per-role `create_worktree(role)`, `commit(role, ...)`, `read_file(role, ...)` |
| New API | `create()`, `commit(message, files)`, `read_file(path)`, `write_file(path, content)`, `remove()` |
| Properties | `worktree_path` (Path), `branch_name` (str) |

### `backend/orchestrator.py`

**Full refactor** — replaced parallel review + phase-based execution with sequential role-based loop.

| Removed | Replacement |
|---------|-------------|
| `_planning_phase()` | Inline planner step in `run()` loop |
| `_execution_loop()` | `while not done: plan → code → test → evaluate` |
| `_call_claude_agent_with_retry()` | Inline logic in `_execute_role()` |
| `_get_agent()` | `RoleResolver.assign(role)` |
| `_read_context_files()` | Context assembled from git diff + CHANGELOG.md + DoD |
| `_run_command()` | Removed (lint/test handled by opencode) |
| `_append_output()`, `_save_step()` | `SessionLogger.log_step()` |

| Added | Details |
|-------|---------|
| `definition_of_done` | Loaded from job config, passed to every role's system prompt |
| `_execute_role()` | Full step execution: resolve agent → build context → run opencode → log step → commit |
| `_build_context()` | Assembles system prompt from: base prompt + DoD + CHANGELOG.md + git diff |
| `_load_agents()` | Loads all agents for a job from DB |
| `_resolve_override()` | Applies job's `agent_overrides` per role |
| Sequential loop | `while not done: plan → code → test → evaluate` |

### `backend/role_resolver.py` (new file)

| Method | Details |
|--------|---------|
| `assign(role)` | Maps `"planner"`/`"coder"`/`"tester"` to job's `*_agent_id` config |
| Returns | Agent dict (model_name, system_prompt, temperature, etc.) |

### `backend/session_logger.py` (new file)

| Method | Details |
|--------|---------|
| `log_step()` | Persists step to `run_steps` table via aiosqlite (async) |
| `_append_changelog()` | Appends Markdown entry to `CHANGELOG.md` in worktree |
| CHANGELOG format | Step number, role, files changed, git commit, summary |

### `backend/database.py`

| Change | Details |
|--------|---------|
| `run_steps` table | Added: `step_number`, `step_type`, `files_changed`, `git_commit` |
| `jobs` table | Added: `definition_of_done TEXT DEFAULT ''` |
| `migrate_database()` | New function; runs `ALTER TABLE` safely (try/except for duplicate columns) |
| Called from | `init_db()` — auto-migrates existing databases |

### `backend/models.py`

| Added | Details |
|-------|---------|
| `JobCreate.definition_of_done` | `str = ""` |
| `JobResponse.definition_of_done` | `str` |
| `StepOut` | New Pydantic model for `GET /runs/{id}/steps` |

### `backend/routers/runs.py`

| Added | Details |
|-------|---------|
| `GET /{run_id}/steps` | Returns `run_steps` ordered by `step_number`, response_model `List[StepOut]` |
| `GET /{run_id}/changelog` | Returns raw `CHANGELOG.md` from worktree |

---

## 2. Frontend Refactor — RunPage Layout

### New Components

#### `frontend/src/components/ActiveStepPanel.tsx`

| Feature | Details |
|---------|---------|
| Role badge | Shows current role (planner/coder/tester) with colored badge |
| Step number | Displays sequential step number |
| Model info | Shows which model is running this step |
| Output stream | Real-time streaming output from WebSocket |
| Override input | Text box + send button — lets user interject at any time |

#### `frontend/src/components/HistoryPanel.tsx`

| Feature | Details |
|---------|---------|
| Collapsible list | Each step is a collapsible card |
| Grouped by step | Shows step number, agent role, step type |
| Expandable output | Click to expand JSON output |

#### `frontend/src/components/HumanInputPanel.tsx`

| Feature | Details |
|---------|---------|
| Disabled state | Grayed out, shows "Waiting for agent request..." |
| Active state | Yellow highlighting on `human_input_required` |
| Agent message | Shows what the agent is asking for |
| Response input | Textarea + submit button |

### Modified Components

| File | Changes |
|------|---------|
| `frontend/src/pages/RunPage.tsx` | Replaced 3-column OutputPanels with vertical layout: PhaseTimeline → ActiveStepPanel → HistoryPanel → HumanInputPanel. Added `steps`, `activeStep`, `streamBuffer`, `humanRequest` state. Updated WS handlers for new `phase_change` payload (includes role, model, step_number). Added `sendOverride` placeholder. |
| `frontend/src/api.ts` | Added `api.runs.getSteps(runId)` and `api.runs.getChangelog(runId)` |
| `frontend/src/types.ts` | Added `RunStep` and `HumanInputRequest` interfaces; updated `WSMessage` with `role`/`model`/`step_number`; updated `RunStatus` union |

### Deprecated (kept for reference, not used)

| File | Status |
|------|--------|
| `frontend/src/components/OutputPanels.tsx` | Replaced by ActiveStepPanel + HistoryPanel |
| `frontend/src/components/HumanInputModal.tsx` | Replaced by HumanInputPanel (persistent, not modal) |

---

## 3. Testing

### New Integration Test

| File | Details |
|------|---------|
| `backend/tests/test_pipeline.py` | Mocks `OpenCodeAgentRunner`, `WorktreeManager`, DB. Verifies sequential loop: planner → coder → tester → evaluate. Asserts run_steps count > 0. |

**Run:**
```bash
cd backend
./venv/bin/python -m pytest tests/test_pipeline.py -v
# 1 passed in 0.34s
```

### Build Verification

| Check | Result |
|-------|--------|
| Frontend `npm run build` | ✅ Zero TypeScript errors |
| Backend Python syntax check | ✅ All `.py` files compile |

---

## 4. Design Documents Created

| File | Purpose |
|------|---------|
| `docs/superpowers/specs/2026-04-29-role-based-synchronous-pipeline-design.md` | Full architecture spec covering pipeline, agent runner, worktree model, session logging, dynamic assignment, DoD, human-in-the-loop, frontend UI |
| `docs/superpowers/plans/2026-04-29-role-based-pipeline.md` | Implementation plan with 9 tasks, file map, code snippets, and spec coverage checklist |

---

## 5. Key Behavioral Changes

| Before | After |
|--------|-------|
| Parallel plan review (coder + tester simultaneously) | Sequential: planner proposes, coder implements, tester validates, planner evaluates |
| 3 isolated worktrees (per role) | 1 shared worktree (all roles see same git state) |
| Fixed agent instances (pre-created on init) | Stateles per-step spawning (context fully assembled by orchestrator) |
| Phase-based execution (coding → testing → evaluating) | Role-based steps with explicit step numbers and CHANGELOG.md |
| Human input as modal overlay | Persistent HumanInputPanel below active step |
| No step-level history API | `GET /runs/{id}/steps` + `GET /runs/{id}/changelog` |
| No DoD tracking | `definition_of_done` on jobs, referenced by planner on every evaluate step |

---

## Files Modified

| File | Changes |
|------|---------|
| `backend/orchestrator.py` | Full refactor — sequential pipeline, `_execute_role()`, `_build_context()` |
| `backend/opencode_agent.py` | **New** — replaces `claude_agent.py` |
| `backend/claude_agent.py` | **Deleted** |
| `backend/worktree_manager.py` | Single worktree API |
| `backend/role_resolver.py` | **New** — role → agent mapping |
| `backend/session_logger.py` | **New** — DB logging + CHANGELOG.md |
| `backend/database.py` | Extended schema + migration |
| `backend/models.py` | `definition_of_done`, `StepOut` |
| `backend/routers/runs.py` | `/steps` and `/changelog` endpoints |
| `backend/tests/test_pipeline.py` | **New** — integration test |
| `frontend/src/pages/RunPage.tsx` | Restructured layout |
| `frontend/src/components/ActiveStepPanel.tsx` | **New** |
| `frontend/src/components/HistoryPanel.tsx` | **New** |
| `frontend/src/components/HumanInputPanel.tsx` | **New** |
| `frontend/src/api.ts` | New endpoints |
| `frontend/src/types.ts` | `RunStep`, `HumanInputRequest`, updated `WSMessage` |
| `docs/PROJECT-STATE-2026-04-29.md` | **New** |
| `docs/CHANGELOG-2026-04-29.md` | **New** |

---

## Commits

```
3b434a7 test: add integration test for sequential pipeline
d6a9f64 feat: restructure RunPage with ActiveStep, History, HumanInput panels
b6c6796 feat: add /steps and /changelog endpoints for run history
6fd2f00 refactor: sequential role-based pipeline replaces parallel execution
ab33a97 feat: add RoleResolver and SessionLogger
3ece5f3 feat: extend db schema for step tracking and DoD
96cd9c9 refactor: simplify WorktreeManager to single shared worktree per run
4c78efb refactor: replace ClaudeAgentRunner with OpenCodeAgentRunner
```
