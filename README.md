# Multi-Agent Studio

A multi-agent LLM orchestration system with a React UI. Coordinates 3 agents — **Planner**, **Coder**, **Tester** — running on Ollama models through a structured planning-review-execution loop with human-in-the-loop support.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Ollama running (default: `http://localhost:11435`)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn main:app --port 8002
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### Ports

| Service | Port | Note |
|---|---|---|
| Backend API | 8002 | Change with `--port` |
| Frontend dev server | 5173 | Vite default |
| Ollama | 11435 | Configure in Settings page |

### First Run

1. Go to **Settings** — set your working directory and Ollama endpoint
2. Go to **Agent Library** — the seed creates 3 default agents (edit as needed)
3. Go to **Jobs Manager** — the seed creates 1 default job (assign agents, set loop mode)
4. Go to **Run Console** — select a job, fill in the feature request, and start a run

## Architecture

```
backend/                  # FastAPI + SQLite + aiosqlite
├── main.py               # App entry point, CORS, WebSocket endpoint
├── database.py            # DB schema and init
├── models.py              # Pydantic v2 models
├── orchestrator.py        # Agent orchestration engine
├── ollama_client.py       # Ollama API client with retry
├── websocket.py           # WebSocket connection manager
├── seed.py                # Default agents + job seeder
└── routers/
    ├── agents.py          # Agent CRUD
    ├── jobs.py            # Job CRUD
    ├── runs.py            # Run start/list/get/resume/stop
    └── settings.py        # Key-value settings

frontend/                 # React 18 + TypeScript + Vite
└── src/
    ├── api.ts             # REST API client
    ├── types.ts           # TypeScript interfaces
    ├── pages/
    │   ├── AgentsPage.tsx       # Agent library
    │   ├── JobsPage.tsx         # Jobs manager
    │   ├── RunPage.tsx          # Run console with WebSocket
    │   ├── HistoryPage.tsx      # Run history
    │   └── SettingsPage.tsx     # Global settings
    └── components/
        ├── AgentForm.tsx        # Agent create/edit modal
        ├── JobForm.tsx          # Job create/edit modal
        ├── ContextBuilder.tsx   # Run context builder
        ├── PhaseTimeline.tsx    # Live phase progress
        ├── OutputPanels.tsx     # Agent output display
        └── HumanInputModal.tsx  # Human-in-the-loop modal
```

## Orchestration Flow

1. **Planning draft** — Planner produces a phased roadmap with definition of done
2. **Planning review** — Coder and Tester review the plan, suggest changes
3. **Planning finalize** — Planner incorporates feedback into final roadmap
4. **Execution loop** — Coder implements a phase → Tester reviews → Planner re-evaluates → continue/adjust/done
5. **Human input** — Any agent can request human input at any phase, pausing the run
