# Session Changelog — 2026-04-28

This document captures all fixes and improvements applied to the `feature/multi-agent-orchestrator` branch during the current session.

---

## 1. Backend Bug Fixes — Orchestrator & API

### `backend/orchestrator.py`

| Issue | Fix |
|-------|-----|
| Resume status restoration lost the previous phase | `_wait_for_human` now captures `previous_status` before switching to `waiting_for_human` and stores it in the human request entry. The resume endpoint restores the exact previous status. |
| `iterations` column in `runs` never incremented | Added `_update_iterations` method. Called at the end of each execution loop iteration. |
| SQL injection risk in `_get_agent` | Replaced string concatenation with a whitelist dictionary `allowed_cols`. Raises `ValueError` on invalid role. |
| Max iterations exhaustion marked as `"done"` | `_execution_loop` now returns `{"roadmap": ..., "completed": bool}`. `run()` checks the flag and marks the run `"failed"` if max iterations were reached without completing all phases. |
| Missing `test_reports` re-append after tester human input | Added `await self._append_output("test_reports", tester_output)` after tester human input is resolved, matching coder behavior. |

### `backend/routers/runs.py`

| Issue | Fix |
|-------|-----|
| Resume set hardcoded `"resuming"` status | Now reads `previous_status` from the human request entry and restores it into the DB. |

### `backend/routers/agents.py`, `routers/jobs.py`, `routers/runs.py`

| Issue | Fix |
|-------|-----|
| `sqlite3.ProgrammingError: Cannot operate on a closed database` | Replaced `await anext(get_db())` (async generator misuse) with direct `await aiosqlite.connect(DB_PATH)` + `db.row_factory = aiosqlite.Row` + manual `finally: await db.close()`. |

### `backend/config.py`

| Issue | Fix |
|-------|-----|
| Settings API returned `TypeError: tuple indices must be integers or slices, not str` | Added `db.row_factory = aiosqlite.Row` to both `get_setting` and `set_setting` so `fetchone()` returns a dict-like Row instead of a plain tuple. |

### `backend/models.py`

| Issue | Fix |
|-------|-----|
| Default Ollama endpoint mismatch (`http://localhost:11434` vs `http://localhost:11435`) | Changed default from `11434` to `11435` to match `database.py`. |

---

## 2. Frontend Bug Fixes — Performance & Configuration

### `frontend/src/App.tsx`

| Issue | Fix |
|-------|-----|
| Navigation between pages showed full loading screen every time | Configured `QueryClient` with `staleTime: 5 * 60 * 1000` (5 min), `gcTime: 10 * 60 * 1000` (10 min), and `refetchOnWindowFocus: false`. Data stays cached and navigation is instant. |

### `frontend/src/pages/AgentsPage.tsx`, `pages/JobsPage.tsx`

| Issue | Fix |
|-------|-----|
| Loading spinner blocked UI even when cached data existed | Changed `if (isLoading)` to `if (isLoading && !data)` so cached data renders immediately. Added subtle `"refreshing..."` pill when `isFetching` is true. |

### `frontend/src/api.ts`

| Issue | Fix |
|-------|-----|
| API calls relied entirely on Vite proxy (relative paths) | Added `BASE` constant reading `VITE_API_BASE_URL` from Vite env, defaulting to empty string. All `fetch` calls now use `` `${BASE}${path}` `` for easy production override. |

---

## 3. Seeding Fix — Duplicate Data on Restart

### `backend/seed.py`

| Issue | Fix |
|-------|-----|
| `python seed.py` ran unconditionally on every container start, creating duplicate agents/jobs | Made seeding idempotent: checks `SELECT COUNT(*) FROM agents` before inserting. If any agents exist, it prints `"Database already seeded... Skipping."` and exits. |

**Cleanup:** Existing duplicate data from prior restarts was cleared by running `docker compose down --volumes` once to create a fresh database, after which the idempotent seed produced exactly 3 agents + 1 job.

---

## 4. Architecture Improvements

### `backend/database.py` — `run_steps` table

| Issue | Fix |
|-------|-----|
| No per-step traceability for agent calls | Added `run_steps` table (`run_id`, `phase`, `agent`, `input`, `output`, `latency_ms`, `error`, `created_at`). Orchestrator writes a row after every agent call via `_save_step`. Enables per-step timing, debugging, and replay. |

### `backend/websocket.py` — `asyncio.Event` registry

| Issue | Fix |
|-------|-----|
| `_wait_for_human` polled the DB every 1 second (`while True: sleep(1)`) | Added `_human_input_events: Dict[int, asyncio.Event]`. Orchestrator `await`s the event; resume endpoint signals it. No polling, instant resume, no wasted DB connections. |

### `backend/orchestrator.py` — Per-phase error handling

| Issue | Fix |
|-------|-----|
| One agent failure killed the entire run | Wrapped each agent call in `_call_agent_with_retry` (1 retry on `OllamaError`). On failure, emits `phase_error` WS event, writes error to `run_steps`, and lets the planner decide retry/skip/fail. The execution loop continues past transient errors. |

### `frontend/src/pages/RunPage.tsx` — WebSocket auto-reconnect

| Issue | Fix |
|-------|-----|
| WebSocket disconnect = frozen UI with no recovery | Added exponential-backoff reconnection (`delay = min(1000 * 2^attempt, 30000)`). Reconnects automatically on close. Stops reconnecting once run reaches `done`/`failed`. |

### `frontend/src/types.ts`

| Issue | Fix |
|-------|-----|
| `phase_error` WS event type not typed | Added `'phase_error'` to `WSMessage.type` union. |

---

## Files Modified

| File | Changes |
|------|---------|
| `backend/orchestrator.py` | Full rewrite: `_call_agent_with_retry`, `_save_step`, `asyncio.Event` wait, per-phase error handling |
| `backend/websocket.py` | `asyncio.Event` registry (`get_human_input_event`, `signal_human_input`, `clear_human_input_event`) |
| `backend/database.py` | Added `run_steps` table |
| `backend/routers/runs.py` | Signals `asyncio.Event` on resume |
| `backend/routers/agents.py` | Direct connection instead of `anext(get_db())` |
| `backend/routers/jobs.py` | Direct connection instead of `anext(get_db())` |
| `backend/config.py` | Added `row_factory = aiosqlite.Row` |
| `backend/models.py` | Default endpoint `11434` → `11435` |
| `backend/seed.py` | Idempotent seed guard |
| `frontend/src/App.tsx` | QueryClient caching config |
| `frontend/src/pages/RunPage.tsx` | WebSocket auto-reconnect, phase_error display |
| `frontend/src/pages/AgentsPage.tsx` | Cached-data-first loading |
| `frontend/src/pages/JobsPage.tsx` | Cached-data-first loading |
| `frontend/src/types.ts` | Added `'phase_error'` to WSMessage |
| `frontend/src/api.ts` | `VITE_API_BASE_URL` support |
| `scripts/setup.py` | Interactive setup script |
| `docker-compose.yml` | Env-var port overrides |
| `.env.example` | Environment configuration template |

---

## 5. Interactive Setup Script (`scripts/setup.py`)

| Feature | Description |
|---------|-------------|
| Ollama model discovery | Fetches `/api/tags` from your Ollama endpoint, lists all available models with sizes |
| Interactive model selection | User picks a model by number |
| Auto-generated agent config | Pre-fills name, role-specific system prompt, temperature, and endpoint based on selection |
| Smart port management | Detects if `8002`/`5173` are occupied, offers next available ports, passes them to `docker compose` via env vars |
| Docker lifecycle | Starts containers only if not already running, waits for backend health before agent creation |
| Idempotent agent creation | Creates agent via backend API after containers are healthy |
| One-command setup | `python scripts/setup.py` — no manual steps needed |

### `docker-compose.yml` — Port & env overrides

| Change | Description |
|--------|-------------|
| Env-var port binding | `ports: - "${BACKEND_PORT:-8002}:8000"` — ports configurable via env |
| Ollama endpoint env | `OLLAMA_ENDPOINT=${OLLAMA_ENDPOINT:-http://host.docker.internal:11435}` |

### `.env.example`

Provides documented template for `OLLAMA_ENDPOINT`, `BACKEND_PORT`, `FRONTEND_PORT`.
