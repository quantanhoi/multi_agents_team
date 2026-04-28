# Multi-Agent Studio — Project State

**Date:** 2026-04-28
**Branch:** `feature/multi-agent-orchestrator`
**Commit:** `ec0aede`
**Status:** Functional — core pipeline working, Ollama Cloud integrated

---

## Overview

Multi-Agent Studio is a multi-agent LLM orchestration system with a React frontend and FastAPI backend. It coordinates 3 specialized agents — Planner, Coder, Tester — through a structured planning-review-execution loop with human-in-the-loop support.

The system has been tested end-to-end with Ollama Cloud models (`kimi-k2.6`, `glm-5.1`, `deepseek-v4-pro`) using Bearer token authentication.

---

## Architecture

```
Frontend (React 18 + Vite + Tailwind)
  ├── TanStack Query for server state
  ├── React Router for navigation
  └── WebSocket for real-time orchestration updates

Backend (FastAPI + Python 3.12)
  ├── SQLite via aiosqlite (async)
  ├── Orchestrator with per-phase retry logic
  ├── WebSocket manager for live updates
  └── Ollama client with Bearer auth support

External
  └── Ollama Cloud API (or local Ollama)
```

### Data Model

- **agents** — name, role, model_name, system_prompt, temperature, ollama_endpoint, api_key
- **jobs** — name, description, planner_agent_id, coder_agent_id, tester_agent_id, loop_mode, max_iterations
- **runs** — job_id, status, feature_request, context, iterations, roadmap, coder_outputs, test_reports, human_requests
- **run_steps** — run_id, phase, agent, input, output, latency_ms, error, created_at
- **settings** — working_dir, ollama_endpoint, ollama_api_key, default_temperature

---

## What's Working

### Core Pipeline
- **Planning Phase** — Planner creates roadmap with phases, DoD, risks, files_needed
- **Review Phase** — Coder and Tester review the plan before execution
- **Execution Loop** — Coder implements → Tester reviews → Planner evaluates
- **Iteration Control** — Up to `max_iterations` (default 5), planner decides continue/adjust/done
- **File Writing** — Coder outputs are written to the working directory

### Human-in-the-Loop
- Agents can request human input mid-run
- Frontend pauses and shows input form
- Resume endpoint signals `asyncio.Event` — no polling
- Status correctly restores to previous phase after resume

### Error Resilience
- Per-phase retry (1 retry on OllamaError, 2 retries on JSON parse failure)
- Transient errors emit `phase_error` WS event but continue the loop
- Planner decides whether to retry, adjust, or fail
- `run_steps` table captures every agent call with latency and error

### Ollama Cloud Integration
- Model discovery via `/api/ollama/models` with Bearer auth
- Per-agent API key support (overrides global setting)
- Tested with `kimi-k2.6`, `glm-5.1`, `deepseek-v4-pro`
- Successfully ran 4+ full iterations through the pipeline

### Frontend
- Instant page navigation with 5-min TanStack Query cache
- Agent CRUD with "Discover Models" button
- Run console with WebSocket live updates
- Settings page with working directory, endpoint, API key, temperature

---

## Known Issues

### Fixed in this session
| Issue | File | Status |
|-------|------|--------|
| Closed database in routers | `routers/*.py` | Fixed — direct `aiosqlite.connect()` |
| Settings API tuple index error | `config.py` | Fixed — added `row_factory` |
| Duplicate agents on restart | `seed.py` | Fixed — idempotent seed guard |
| Iterations never incremented | `orchestrator.py` | Fixed — `_update_iterations()` |
| Max iterations marked done | `orchestrator.py` | Fixed — returns `completed` flag |
| `human_input_request` as string crashes orchestrator | `orchestrator.py` | Fixed — type check + normalization |
| `human_input_request` dict missing `requested_by` key | `orchestrator.py` | Fixed — `.get()` with defaults |

### Still Present
| Issue | Impact | Notes |
|-------|--------|-------|
| Evaluating phase occasionally times out (360s) | Run retries or fails | Ollama Cloud `kimi-k2.6` sometimes doesn't respond within 120s timeout × 3 retries. Run continues on retry. |
| Evaluating phase sometimes returns non-JSON | Run retries | Planner occasionally returns plain text instead of JSON. Retry with "return JSON only" prompt usually fixes it. |
| Tester flags missing pytest as blocking bug | Extra iterations | Tester reports `pytest not installed` as a high-severity bug, causing the loop to continue unnecessarily. Consider adding pytest to the environment or adjusting tester prompt. |
| Ollama endpoint hardcoded to `https://ollama.com` | May not match user's actual endpoint | Changed from `https://api.ollama.cloud` due to expired SSL cert. User should update to their actual endpoint in Settings. |

---

## Configuration

### Environment Variables (`.env`)
```bash
OLLAMA_ENDPOINT=https://ollama.com          # Your Ollama endpoint
OLLAMA_API=sk-your-key-here                  # Your Ollama Cloud API key
BACKEND_PORT=8002                            # Host port for backend
FRONTEND_PORT=5173                           # Host port for frontend
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

### Settings
- `GET /api/settings` — Get current settings
- `PUT /api/settings` — Update settings

### Agents
- `GET /api/agents` — List all agents
- `POST /api/agents` — Create agent
- `PUT /api/agents/{id}` — Update agent
- `DELETE /api/agents/{id}` — Delete agent

### Jobs
- `GET /api/jobs` — List all jobs
- `POST /api/jobs` — Create job
- `PUT /api/jobs/{id}` — Update job
- `DELETE /api/jobs/{id}` — Delete job

### Runs
- `POST /api/runs` — Start a run (returns immediately, runs in background)
- `GET /api/runs` — List runs
- `GET /api/runs/{id}` — Get run details
- `POST /api/runs/{id}/resume` — Resume a run with human input
- `POST /api/runs/{id}/stop` — Stop a run

### Ollama
- `GET /api/ollama/models` — List available models from Ollama endpoint

### WebSocket
- `WS /ws/{run_id}` — Subscribe to real-time run updates

---

## Files

| Directory | Purpose |
|-----------|---------|
| `backend/` | FastAPI app, orchestrator, database, routers |
| `frontend/` | React 18 + Vite + Tailwind app |
| `scripts/` | `setup.py` — interactive one-command setup |
| `docs/` | Changelogs and project documentation |
| `data/` | SQLite database (mounted volume in Docker) |

---

## Quick Start

```bash
# 1. Set your Ollama Cloud API key
cp .env.example .env
# Edit .env and set OLLAMA_API=your-key

# 2. Start everything
docker compose up -d

# 3. Open UI
open http://localhost:5173

# Or use the interactive setup script
python scripts/setup.py
```

---

## Testing

Run 2 (tested 2026-04-28) executed successfully through 2 iterations:
- Planner produced a 2-phase roadmap (Implementation + Testing)
- Coder created `calculator.py` with `add()` function
- Tester validated with pass status
- Evaluating decided to continue, then the run completed

All 3 Ollama Cloud models responded correctly with structured JSON following their system prompt schemas.

---

## Next Steps (Suggested)

1. **Update Ollama endpoint** — Change from `https://ollama.com` to your actual Ollama Cloud endpoint in Settings
2. **Add pytest to working directory** — Prevents tester from flagging it as a blocking bug
3. **Consider shorter evaluating timeouts** — 120s × 3 retries = 6 min per evaluating call; may want to reduce for faster feedback
4. **Add run cancellation** — Currently only `stop_run` exists; no mid-phase cancellation
5. **Add run logs viewer** — Frontend only shows run status, not the full `run_steps` trace
