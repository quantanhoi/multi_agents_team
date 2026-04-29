# Role-Based Synchronous Pipeline — Design Document

**Date:** 2026-04-29  
**Topic:** Orchestrator refactor from parallel review to sequential role-based pipeline  
**Status:** Approved  
**Author:** Product + AI design session

---

## 1. Overview & Goals

The orchestrator engine is refactored from a parallel-review / sequential-execution model to a **strictly sequential, role-based pipeline** with dynamic assignment of 2–3 opencode instances to Planner, Coder, and Tester roles.

### Goals
- Replace parallel planning review with synchronous Planner → Coder → Tester → Planner handoff  
- Enable dynamic role assignment: a GLM5.1 instance can be Planner in step 1 and Tester in step 7  
- Reduce complexity by using a **single shared worktree** per run (sequential access, no isolation conflicts)  
- Keep instances **stateless per-step** (spawn per role invocation, full context assembled by orchestrator)  
- Persist a per-run `CHANGELOG.md` alongside git history for explicit step narrative  
- Allow human escalation at any role step; frontend shows active step + history + human input panel  

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                       FRONTEND                             │
│  RunPage.tsx                                               │
│  ├── PhaseTimeline (horizontal: step badges)               │
│  ├── Active Step Panel (current role, streaming output) │
│  ├── History Panel (collapsible past steps)               │
│  └── Human Input Panel (disabled until escalation)        │
└──────────────────────┬─────────────────────────────────────┘
                       │  WebSocket (ws_manager)
                       ▼
┌──────────────────────────────────────────────────────────┐
│                       BACKEND                              │
│  FastAPI routers (runs.py, agents.py, jobs.py)           │
│  ├── Orchestrator (refactored: sequential pipeline)      │
│  │   ├── DynamicRoleResolver (maps role → agent instance) │
│  │   ├── OpenCodeAgentRunner (spawn per step)            │
│  │   ├── WorktreeManager (single shared worktree/run)     │
│  │   └── SessionLogger (run_steps + CHANGELOG.md)         │
│  └── WebSocket: ws_manager.send(run_id, event)             │
└──────────────────────────────────────────────────────────┘
```

### Core file changes

| File | Action | Scope |
|------|--------|-------|
| `orchestrator.py` | Refactor execution loop | High |
| `claude_agent.py` | Rename/generalize → `opencode_agent.py` | Medium |
| `worktree_manager.py` | Add single-worktree mode | Medium |
| `models.py` | Add `workflow_mode`, `DoD`, `step_number` | Low |
| `database.py` | Extend `run_steps` schema | Low |
| `websocket.py` | No changes (reused) | None |
| `frontend/src/pages/RunPage.tsx` | Restructure layout | High |

---

## 3. Pipeline & Data Flow

### Sequential execution loop (strictly single-threaded per run)

```
Iteration N:
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ PLANNER  │───→│  CODER   │───→│  TESTER  │───→│ PLANNER  │
  │ (any     │    │ (any     │    │ (any     │    │ (any     │
  │  model)  │    │  model)  │    │  model)  │    │  model)  │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
       │               │                │               │
   plan.json     code + files     test_report     (check DoD?)
```

### State machine per run

| Phase | Description |
|-------|-------------|
| `planning` | Planner produces plan.json + step-level DoD |
| `coding` | Coder implements code, commits changes |
| `testing` | Tester runs tests, produces test_report |
| `evaluating` | Planner checks: does state satisfy top-level DoD? |
| `done` | Planner confirms top-level DoD is met |
| `waiting_for_human` | Any role escalated; pipeline frozen |
| `failed` | Max iterations reached without DoD satisfaction |

### Decision points
- After `testing`, Planner evaluates: **"Is the top-level DoD satisfied?"**  
  - **Yes** → `done`  
  - **No** → Planner proposes next step, picks area by priority (not pre-ordered)  
  - **Human needed** → `waiting_for_human`  

### Git as the handoff mechanism
- Every role commits at the end of its step  
- Next role sees full commit history + `git diff`  
- Orchestrator loads diff + `CHANGELOG.md` into context  

---

## 4. Agent Runner & Worktree Model

### OpenCodeAgentRunner (formerly ClaudeAgentRunner)

Replaced to run **opencode CLI with superpowers plugin** instead of Claude Code:

```python
class OpenCodeAgentRunner:
    def run(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = "glm5.1",        # from role assignment
        role: str = "planner",         # injected into prompt
    ) -> dict:
        # Runs: opencode -p --model <model> --role <role> <prompt>
        # In the shared worktree directory
```

**Spawn per invocation:** Every step creates a fresh `opencode` subprocess. No long-running sessions. Context is fully assembled by the orchestrator via `system_prompt`.

### Worktree Model — Single shared worktree per run

- Create ONE worktree: `run-{id}` (not per role)  
- Every role runs `opencode` inside this directory  
- Each role commits its changes before handoff  
- Next role runs `git log --oneline -3` + `git diff HEAD~1` to see what changed  
- All roles share the same branch: `agent/run-{id}`  

**Why shared?**
- Coder must read plan.json from Planner  
- Planner (re-entry) must see Coder commits and Tester test results  
- Sequential access means no file conflicts  
- Git diff is cheaper than cross-worktree file copies  

### Why not stateful long-running instances?

We discussed this. Option A (long-running) preserves model context but adds process lifecycle complexity (crashes, reconnections, message routing). Option B (stateless per step) is simpler, deterministic, and safe to retry. The orchestrator assembles full context from `run_steps` + `CHANGELOG.md` + git diff. If context windows become an issue later, session pooling can be added without changing the orchestrator contract.

---

## 5. Session Change Log

### Purpose
Since instances are stateless per step, every role needs explicit narrative context beyond git diff.

### `run_steps` table (extended)

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | PK |
| `run_id` | INTEGER | FK |
| `step_number` | INTEGER | Sequential: 1, 2, 3... |
| `role` | TEXT | `planner`, `coder`, `tester` |
| `step_type` | TEXT | `plan`, `code`, `test`, `evaluate` |
| `input_summary` | TEXT | Brief what was asked |
| `output_summary` | TEXT | Brief what was produced |
| `files_changed` | JSON | Array of file paths |
| `git_commit` | TEXT | Commit hash, or null |
| `status` | TEXT | `success`, `error`, `needs_human` |
| `latency_ms` | INTEGER | Execution time |
| `error` | TEXT | Error message, or null |

### `CHANGELOG.md` (auto-generated in worktree root)

Every step appends:

```markdown
## Step 3 — Coder (kimi-k2.6)
- Files changed: `backend/api/users.py`, `tests/test_users.py`
- Commit: `a1b2c3d`
- Summary: Implemented POST /users endpoint with validation
```

This file is:
- Written by orchestrator after each step  
- Committed alongside code changes  
- Loaded into the next role's `system_prompt` as *narrative context*  

### Context assembly for each step

```python
system_prompt = f"""
You are the {role} for this project.

Project definition of done: {top_level_dod}

---
Step history so far (from CHANGELOG.md):
{changelog_content}

---
Git diff from previous step:
{git_diff}

---
Current task:
{step_prompt}
"""
```

---

## 6. Dynamic Role Assignment

### Problem
A run can have 2–3 instances of opencode connected to Ollama Cloud. At any step, Planner/Coder/Tester must be assigned to an available instance.

### Solution: RoleResolver

```python
class RoleResolver:
    def __init__(self, job: JobConfig, agents: list[AgentConfig]):
        self.agents = {a.id: a for a in agents}
        self.job = job

    def assign_role(self, role: str) -> AgentConfig:
        # Map from job config's per-role agent IDs
        col = {"planner": self.job.planner_agent_id,
               "coder": self.job.coder_agent_id,
               "tester": self.job.tester_agent_id}[role]
        return self.agents[col]
```

### Configurable mappings

Job config stores per-role model assignment:

```json
{
  "role_assignments": {
    "planner": {"model": "glm5.1", "instance": "instance-1"},
    "coder": {"model": "kimi-k2.6", "instance": "instance-2"},
    "tester": {"model": "deepseek-v4-pro", "instance": "instance-3"}
  }
}
```

Default: use `planner_agent_id`, `coder_agent_id`, `tester_agent_id` from existing `JobCreate` model. These continue to work — the resolver maps IDs.

---

## 7. Definition of Done (DoD)

### Top-level DoD (user-provided)

At job creation, the user supplies the overall project goal:
> "A fully functional user management API with CRUD endpoints, JWT auth, and unit tests."

Planner always references this when evaluating whether to stop or continue.

### Step-level DoD (planner-generated)

Planner writes a `definition_of_done` for each step before execution:

```json
{
  "step_number": 3,
  "role": "coder",
  "dod": "Implement POST /users with request validation. Must return 201 on success, 400 on invalid input."
}
```

Tester verifies against this DoD. If not met, Planner retries or adjusts.

---

## 8. Human-in-the-Loop

### Escalation model
Any role can emit a `human_input_request` in its output. Example:

```json
{"human_input_request": {
  "requested_by": "coder",
  "message": "Need a screenshot of the form layout for this validation flow",
  "input_type": "text+file"
}}
```

### Orchestrator behavior on escalation
1. Pipeline freezes at current step  
2. `run_steps` status = `needs_human`  
3. WebSocket pushes `human_input_required` event  
4. Frontend enables Human Input Panel  
5. Human submits → backend writes synthetic `human_override` step  
6. Orchestrator resumes the **same role** with human response appended to its context  

### Response types
- `text` — freeform text area  
- `text+file` — text area + file upload  
- `screenshot` — file restricted to images  
- `yes-no` — toggle switch  
- `dod-approval` — checkbox ("Approve this plan")  

---

## 9. Frontend UI — Active Step, History, Human Input

### RunPage.tsx layout

```
┌───────────────────────────────────────────────────────┐
│ PhaseTimeline (horizontal bar)                         │
│  Step 1 ✓ → Step 2 ✓ → [Step 3 ⟳] → Step 4 ○        │
└───────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────┐
│ Active Step Panel                                      │
│  ├─ Role badge: [Coder] (model: kimi-k2.6)           │
│  ├─ Status: running since 14:32:05                     │
│  ├─ Output stream:                                     │
│  │   [live text / structured JSON preview]             │
│  └─ Override input:                                  │
│      [Type message...]         [Send]                │
│      (always visible, lets user interject anytime)   │
└───────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────┐
│ History Panel (collapsible)                           │
│  ├─ ▼ Step 1: Planner (glm5.1) | plan.json           │
│  ├─ ▼ Step 2: Tester (deepseek) | 2 bugs found       │
│  └─ ▼ Step 3: Planner (glm5.1) | revised plan        │
└───────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────┐
│ Human Input Panel (disabled by default, grayed)        │
│  Message: "Waiting for agent request..."               │
│  Submit: [disabled button]                           │
│                                                        │
│  ON escalation:                                        │
│  ├─ Active + highlighted                               │
│  ├─ Agent message displayed                            │
│  ├─ Text area / file upload (context-aware)           │
│  └─ [Submit Response]                                  │
└───────────────────────────────────────────────────────┘
```

### WebSocket events mapping

| Event | UI Effect |
|-------|-----------|
| `phase_change` | Update PhaseTimeline, swap Active Step Panel badge |
| `agent_output` | Append content to Active Step Panel output stream |
| `human_input_required` | Activate Human Input Panel, auto-scroll to viewport |
| `done` | Freeze Active Step, show "✅ All phases complete" banner |
| `failed` | Freeze Active Step, show "❌ Failed" banner with error |

### Override input behavior
- User can type a message in the chat box at any time  
- Backend writes it as a `human_override` step  
- Next role receives it in its `system_prompt` under `--- HUMAN OVERRIDE`  
- If the pipeline is in `waiting_for_human`, the override acts as the response

---

## 10. Error Handling & Retry

### Per-step retry (`max_retries` per role, default 1)

Current `_call_claude_agent_with_retry` logic is preserved:
1. Spawn `opencode`  
2. Check exit code  
3. If error → retry once  
4. If still failing → `run_steps.status = "error"`, WebSocket `phase_error`  
5. Orchestrator decides: continue to next step (if non-fatal) or escalate to human  

### Orchestrator-level recovery
- If any role fails after retries, Planner is invoked with an `error_evaluation` system prompt  
- Planner decides: retry same role, skip, or request human assistance  

### Git rollback
- Each step commits independently  
- `git revert` or `git reset --soft HEAD~1` is possible if a step must be undone  
- Not automated in v1; human can trigger via UI

---

## 11. Database Changes

### Extend `run_steps`

Migration (SQLite):

```sql
ALTER TABLE run_steps ADD COLUMN step_number INTEGER;
ALTER TABLE run_steps ADD COLUMN step_type TEXT CHECK(step_type IN ('plan','code','test','evaluate'));
ALTER TABLE run_steps ADD COLUMN files_changed TEXT; -- JSON array
ALTER TABLE run_steps ADD COLUMN git_commit TEXT;
```

### Extend `jobs`

```sql
ALTER TABLE jobs ADD COLUMN definition_of_done TEXT DEFAULT '';
```

The existing `loop_mode` field (`automatic`) is deprecated by this refactor. All runs now use the sequential pipeline by default. The field may be removed in a future migration once confirmed stable.

---

## 12. API Changes

### `POST /api/runs` (RunStart)

Current model supports `RunStart` with `job_id` and `feature_request`. The orchestrator always runs the sequential pipeline (this refactor replaces the legacy parallel mode).

### `POST /api/runs/{run_id}/human_response`

Already exists. Preserved. Payload extended with `uploaded_files`.

### New: `GET /api/runs/{run_id}/steps`

Returns `run_steps` ordered by `step_number` for the Run Console history panel.

### New: `GET /api/runs/{run_id}/changelog`

Returns raw `CHANGELOG.md` content from the worktree.

---

## 13. Testing Strategy

### Backend
- **Unit:** `RoleResolver` assignment logic  
- **Unit:** `OpenCodeAgentRunner` command construction + exit code parsing  
- **Integration:** Full pipeline run with mock `opencode` subprocess (return fixed JSON, verify step count / git commits)  
- **Integration:** WebSocket events fire in correct order

### Frontend
- **Unit:** PhaseTimeline renders badges correctly from step array  
- **Unit:** Human Input Panel enables/disables on WebSocket events  
- **E2E (manual):** Create job → run → verify streaming output → inject override → verify resume

---

## 14. Rollout Plan

| Step | Action |
|------|--------|
| 1 | Refactor `orchestrator.py`: replace execution loop with sequential pipeline |
| 2 | Rename `claude_agent.py` → `opencode_agent.py`, update command to `opencode` |
| 3 | Simplify `worktree_manager.py`: single worktree per run |
| 4 | Extend database schema (`run_steps`, `jobs`) |
| 5 | Add `RoleResolver` + dynamic assignment |
| 6 | Implement session logging (`CHANGELOG.md` auto-generation) |
| 7 | Update `models.py` with `workflow_mode` + `definition_of_done` |
| 8 | Frontend: restructure RunPage.tsx with Active Step / History / Human Input |
| 9 | Add `/steps` and `/changelog` endpoints |
| 10 | Manual E2E test: create run → verify step-by-step progression |
| 11 | Update docs (`GETTING-STARTED.md`) |

---

## 15. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `opencode` CLI not as stable as `claude` | Keep fallback: if `opencode` not found, fail fast with clear error |
| Context window overflow on long runs | Summarize `CHANGELOG.md` after N steps; truncate git diff to last 3 commits |
| Git conflicts in shared worktree | Sequential access prevents conflicts; single branch |
| Human input panel abused (users type non-escalation messages) | Override works as a "hint" system; agent decides whether to act on it |
| Model response not valid JSON | Already handled: retry with "return valid JSON only" prompt |

---

## 16. Open Questions (resolved during design session)

**Q: Fixed or configurable role-to-model mapping?**  
A: Configurable per job. Default from existing `planner_agent_id`, `coder_agent_id`, `tester_agent_id`.

**Q: Shared worktree or per-role worktree?**  
A: Shared per run. Sequential access guarantees no conflicts. Git history is the handoff.

**Q: Stateful long-running instances or stateless per-step?**  
A: Stateless per-step (simpler, safer). Context assembled by orchestrator. Session pooling can be added later without contract changes.

**Q: Human approval at every step or escalation-only?**  
A: Escalation-only. But user can interject at any time via override input.

**Q: Frontend: how are active step and human input shown?**  
A: Active Step Panel always shows current role + streaming output. Human Input Panel starts disabled; activates on `human_input_required` event. History Panel shows complete log of finished steps.
