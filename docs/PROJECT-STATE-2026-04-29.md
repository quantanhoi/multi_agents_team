# Multi-Agent Studio — Project State

**Date:** 2026-04-29
**Branch:** `feature/multi-agent-orchestrator`
**Commit:** `3b434a7`
**Status:** Role-based synchronous pipeline implemented and tested

---

## Overview

Multi-Agent Studio is a multi-agent LLM orchestration system with a React frontend and FastAPI backend. It coordinates 2–3 opencode instances (Planner, Coder, Tester) through a **strictly sequential, role-based pipeline** with dynamic assignment, human-in-the-loop support, and session logging.

The system has been tested end-to-end with Ollama Cloud models (`kimi-k2.6`, `glm-5.1`, `deepseek-v4-pro`) using Bearer token authentication.

## What's New (2026-04-29)

The orchestrator was refactored from a parallel-review/sequential-execution model to a **synchronous sequential pipeline**.

### Architecture Change

```
OLD (parallel review):
Planner draft ─┬→ Coder review
             └→ Tester review ──→ Planner finalize ──→ Execution loop

NEW (sequential handoff):
Planner → Coder → Tester → Planner → ... (loop until DoD met)
```

### New Components

| Component | File | Purpose |
|-----------|------|---------|
| OpenCodeAgentRunner | `backend/opencode_agent.py` | Runs `opencode` CLI per step with configurable model |
| RoleResolver | `backend/role_resolver.py` | Maps planner/coder/tester roles to agent instances |
| SessionLogger | `backend/session_logger.py` | Logs every step to DB + auto-generates `CHANGELOG.md` |
| ActiveStepPanel | `frontend/src/components/ActiveStepPanel.tsx` | Shows current role, streaming output, override input |
| HistoryPanel | `frontend/src/components/HistoryPanel.tsx` | Collapsible list of completed steps |
| HumanInputPanel | `frontend/src/components/HumanInputPanel.tsx` | Persistent panel; activates on escalation |

### Removed/Replaced Components

| Old | Replacement | Reason |
|-----|-------------|--------|
| `ClaudeAgentRunner` (via `claude` CLI) | `OpenCodeAgentRunner` (via `opencode` CLI) | Switched to open-source agent runtime |
| 3 worktrees per run (`run-{id}-{role}`) | Shared worktree (`run-{id}`) | Sequential access, no conflicts, git is handoff |
| Parallel plan review (coder + tester) | Sequential evaluation by returning planner | Simpler, deterministic, no race conditions |
| Phase-based execution loop | Iteration-based sequential loop | Planner decides continue/done after each coder+tester pass |

---

## Architecture

```
Frontend (React 18 + Vite + Tailwind)
  ├── TanStack Query for server state
  ├── React Router for navigation
  └── WebSocket for real-time run updates
    ├── PhaseTimeline (horizontal step badges)
    ├── ActiveStepPanel (current role + output)
    ├── HistoryPanel (collapsible past steps)
    └── HumanInputPanel (escalation input)

Backend (FastAPI + Python 3.12)
  ├── SQLite via aiosqlite (async)
  ├── Sequential Orchestrator (Planner→Coder→Tester→Planner)
  ├── RoleResolver — maps role → agent config per job
  ├── SessionLogger — DB steps + CHANGELOG.md
  ├── OpenCodeAgentRunner — per-step subprocess spawning
  ├── WorktreeManager — single shared git worktree/run
  ├── WebSocket manager for live updates
  └── Ollama client with Bearer auth support

External
  └── Ollama Cloud API (or local Ollama)
  └── opencode CLI (with superpowers plugin)
```

### Data Model

- **agents** — name, role, model_name, system_prompt, temperature, ollama_endpoint, api_key
- **jobs** — name, description, planner_agent_id, coder_agent_id, tester_agent_id, loop_mode (deprecated), max_iterations, **definition_of_done**
- **runs** — job_id, status, feature_request, context, iterations, roadmap, coder_outputs, test_reports, human_requests
- **run_steps** (extended) — run_id, **step_number**, **step_type**, phase, agent, input, output, latency_ms, error, **files_changed**, **git_commit**, created_at
- **settings** — working_dir, ollama_endpoint, ollama_api_key, default_temperature

---

## Pipeline & Data Flow

```
User provides top-level Definition of Done (DoD)
    │
    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   PLANNER    │────→│    CODER     │────→│   TESTER     │────→│   PLANNER    │
│ (any model)  │     │ (any model)  │     │ (any model)  │     │ (evaluate)   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
      │                    │                    │                     │
  plan.json            code + files          test report          DoD met?
                                                          ┌─────────┬─────────┐
                                                          │  Yes    │   No    │
                                                          │→  done   │→ next  │
                                                          └─────────┴─────────┘
```

### Context Assembly

Each step receives a system prompt assembled from:
1. Base system prompt from agent config
2. Top-level Definition of Done
3. Full `CHANGELOG.md` history (narrative context)
4. `git diff HEAD~1..HEAD` (recent code changes)
5. The current task prompt

### Role Assignment

Roles are dynamically assigned per job:
- Default: `planner` → job's `planner_agent_id` agent → GLM5.1
- Default: `coder` → job's `coder_agent_id` agent → KIMI K2.6
- Default: `tester` → job's `tester_agent_id` agent → DeepSeek v4 Pro
- Same model can perform multiple roles (stateless per step)

---

## What's Working

### Core Pipeline
- **Planning** — Planner creates plan.json + step-level DoD
- **Coding** — Coder implements code, commits changes
- **Testing** — Tester runs tests, produces test report
- **Evaluating** — Planner checks if top-level DoD is satisfied
- **Iteration** — Planner proposes next step; repeats until done or max iterations

### Session Logging
- Every step tracked in `run_steps` table with latency, error, files_changed, git_commit
- Auto-generated `CHANGELOG.md` committed alongside code changes
- `GET /api/runs/{id}/steps` — retrieve full step history
- `GET /api/runs/{id}/changelog` — retrieve live markdown log

### Git Worktree Model
- Single worktree per run (`run-{id}`) shared by all roles
- Each role commits before handoff
- Next role reads commit history + git diff for context

### Human-in-the-Loop (Updated UI)
- Frontend panels: ActiveStep, History, HumanInput (persistent, not modal)
- Override input always visible — user can interject at any time
- HumanInput panel is disabled/grayed by default; activates yellow on escalation
- WebSocket events: `phase_change`, `agent_output`, `human_input_required`, `done`, `failed`

### Error Resilience
- Per-step retry (1 retry on OpenCodeAgentError)
- Transient errors emit `phase_error` but loop continues
- Planner decides retry/skip/fail on error
- `run_steps` captures every call with latency and error

### Ollama Cloud Integration
- Model discovery via `/api/ollama/models` with Bearer auth
- Per-agent API key support (overrides global setting)
- Tested with `kimi-k2.6`, `glm-5.1`, `deepseek-v4-pro`

### Frontend
- Restructured RunPage: PhaseTimeline → ActiveStepPanel → HistoryPanel → HumanInputPanel
- WebSocket streaming output in ActiveStepPanel
- Collapsible history of all prior steps
- ContextBuilder, Settings, Agent CRUD, Job CRUD unchanged

---

## Known Issues

### New (from refactor)

| Issue | Impact | Notes |
|-------|--------|-------|
| `opencode` CLI availability | Startup fails if not installed | `npm install -g opencode` or equivalent required |
| Context window overflow on long runs | Long prompts | CHANGELOG.md is truncated after N steps; git diff limited to last 3 commits |
| No fallback if `opencode` CLI unsupported | Must use opencode | Cannot fall back to raw LLM API without code changes |

### Still Present

| Issue | Impact | Notes |
|-------|--------|-------|
| Evaluating phase occasionally times out (360s) | Run retries or fails | Ollama Cloud `kimi-k2.6` sometimes doesn't respond within 120s timeout × 3 retries |
| Evaluating phase sometimes returns non-JSON | Run retries | Retry with "return JSON only" prompt usually fixes |
| Tester flags missing pytest as blocking bug | Extra iterations | Consider adding pytest to environment or adjusting tester prompt |
| Ollama endpoint may need updating | Connection failures | User should verify endpoint in Settings |

---

## Configuration

### Environment Variables (`.env`)
```bash
OLLAMA_ENDPOINT=https://ollama.com          # Your Ollama endpoint
OLLAMA_API=sk-your-key-here                  # Your Ollama Cloud API key
BACKEND_PORT=8002                            # Host port for backend
FRONTEND_PORT=5173                           # Host port for frontend
PROJECT_DIR=./projects                       # Project workspace
```

### Default Agents (Seeded)
| Name | Role | Model | Endpoint |
|------|------|-------|----------|
| Kimi Planner | planner | `kimi-k2.6` | `https://ollama.com` |
| GLM Coder | coder | `glm-5.1` | `https://ollama.com` |
| DeepSeek Tester | tester | `deepseek-v4-pro` | `https://ollama.com` |

All agents have the API key set from `.env.example`.

---

## API Endpoints

### Runs (extended)
- `POST /api/runs` — Start a run (sequential pipeline)
- `GET /api/runs` — List runs
- `GET /api/runs/{id}` — Get run details
- `POST /api/runs/{id}/resume` — Resume with human input
- `POST /api/runs/{id}/stop` — Stop a run
- `GET /api/runs/{id}/steps` — List all steps for a run
- `GET /api/runs/{id}/changelog` — Get `CHANGELOG.md` content

### Agents, Jobs, Settings, Ollama — unchanged

---

## Frontend Components

| Component | Status | File |
|-----------|--------|------|
| PhaseTimeline | Extended (shows sequential phases) | `frontend/src/components/PhaseTimeline.tsx` |
| ActiveStepPanel | **New** | `frontend/src/components/ActiveStepPanel.tsx` |
| HistoryPanel | **New** | `frontend/src/components/HistoryPanel.tsx` |
| HumanInputPanel | **New** (replaces modal) | `frontend/src/components/HumanInputPanel.tsx` |
| OutputPanels | Deprecated (replaced by HistoryPanel) | `frontend/src/components/OutputPanels.tsx` |
| HumanInputModal | Deprecated (replaced by panel) | `frontend/src/components/HumanInputModal.tsx` |

---

## Quick Start

```bash
# 1. Set your Ollama Cloud API key
cp .env.example .env
# Edit .env and set OLLAMA_API=your-key

# 2. Install opencode CLI (if not already)
npm install -g opencode

# 3. Start everything
docker compose up -d

# 4. Open UI
open http://localhost:5173

# Or use the interactive setup script
python scripts/setup.py
```

---

## Testing

- **Integration test:** `backend/venv/bin/python -m pytest backend/tests/test_pipeline.py -v` ✅ (1 passing)
- **Frontend build:** `cd frontend && npm run build` ✅ (zero TypeScript errors)

---

## Next Steps (Suggested)

1. **Add session pooling** — If context windows grow too large, reuse model instances across steps
2. **Add override endpoint** — Dedicated API for interjecting hints without human escalation
3. **Add run cancellation** — Mid-phase cancellation beyond `stop_run`
4. **Add step-level DoD UI** — Show each step's definition of done in the frontend
5. **Add CHANGELOG preview** — Inline view of auto-generated changelog in HistoryPanel
