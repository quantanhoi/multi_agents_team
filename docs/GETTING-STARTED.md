# Getting Started with Multi-Agent Studio

This guide walks you through running Multi-Agent Studio for the first time — from zero to your first orchestrated run.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- An [Ollama Cloud](https://ollama.com/) API key (free tier works)
- (Optional) An existing local project you want agents to work on

---

## Step 1 — Clone & Enter the Project

```bash
git clone https://github.com/quantanhoi/multi_agents_team.git
cd multi_agents_team
# Or if you already have the repo
cd /path/to/multi_agents_team
```

---

## Step 2 — Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and set your values
nano .env   # or vim, code, etc.
```

### Required variables

| Variable | What to put | Example |
|----------|-------------|---------|
| `OLLAMA_API` | Your Ollama Cloud API key | `sk-...` |
| `OLLAMA_ENDPOINT` | Ollama API URL | `https://ollama.com` |

### Optional variables

| Variable | What to put | Default |
|----------|-------------|---------|
| `BACKEND_PORT` | Host port for backend API | `8002` |
| `FRONTEND_PORT` | Host port for web UI | `5173` |
| `PROJECT_DIR` | Path to your existing project folder | `./projects` |

**Finding your Ollama Cloud API key:**
1. Go to https://ollama.com/settings
2. Copy your API key
3. Paste it into `.env` as `OLLAMA_API=your-key-here`

---

## Step 3 — Start the System

```bash
docker compose up -d
```

This starts two containers:
- **Backend** (`multi-agent-backend`) — FastAPI on port `8002`
- **Frontend** (`multi-agent-frontend`) — Vite React on port `5173`

Wait ~10 seconds for the backend to seed the database, then verify:

```bash
curl http://localhost:8002/api/health
# Expected: {"status":"ok"}
```

---

## Step 4 — Open the UI

Open http://localhost:5173 in your browser.

You should see three default agents already created:

| Agent | Role | Model |
|-------|------|-------|
| Kimi Planner | Planner | `kimi-k2.6` |
| GLM Coder | Coder | `glm-5.1` |
| DeepSeek Tester | Tester | `deepseek-v4-pro` |

And one default job: **Default Full-Stack Feature**

---

## Step 5 — Run Your First Job (No Project)

1. Go to **Run Console**
2. Select the **Default Full-Stack Feature** job
3. Enter a feature request, e.g.:
   > "Create a Python function that adds two numbers and returns the result"
4. Click **Run**

The run starts in the background. You will see live phase updates via WebSocket:
- Sequential role steps: `planning` → `coding` → `testing` → `evaluating` (repeats up to 5 times)
- Each step shows the active agent, model, and streaming output
- Completed steps appear in the History panel
- The override input box lets you interject at any time

A typical run takes 3–10 minutes depending on model response times.

---

## Step 6 — Link an Existing Project (Optional)

If you have an existing codebase you want the agents to read and modify, follow these steps.

### 6a — Set the project directory

In your `.env` file:

```bash
PROJECT_DIR=/absolute/path/to/your/project
```

Then restart:

```bash
docker compose up -d
```

The backend container now mounts your project folder at `/workspace`.

### 6b — Tell the backend where to look

1. Go to **Settings** in the UI
2. Set **Working Directory** to `/workspace`
3. Save

> The path `/workspace` is the mount point inside the Docker container. It maps to whatever `PROJECT_DIR` you set on your host.

### 6c — Select files when starting a run

1. Go to **Run Console**
2. In the **Files** field, enter paths relative to `PROJECT_DIR`:
   ```
   src/app.py, src/models.py, README.md
   ```
3. Fill in the feature request and click **Run**

The Planner will see the file contents in its context. The Coder will write modified files back to your project directory.

### Example

```bash
# On your host
PROJECT_DIR=/home/edward/my-web-app

# In Settings UI
Working Directory = /workspace

# In Run Console Files field
src/components/Header.tsx, src/utils/api.ts
```

---

## Step 7 — Verify Agents Can See Your Files

Start a run with a file selected, then check the backend logs:

```bash
docker logs -f multi-agent-backend
```

Look for the planning phase — you should see the file content included in the prompt context.

---

## Understanding the Run Lifecycle

```
User Request (+ Definition of Done)
    |
    ▼
┌──────────────────────────────────────────────────────────┐
│  Iteration 1                                             │
│  +---------------+   +---------------+   +---------------+ │
│  │    PLANNER    │──→│     CODER     │──→│   TESTER      │ │
│  │ Creates plan  │   │ Implements  │   │ Tests code    │ │
│  │ + step-level  │   │ + commits   │   │ + reports     │ │
│  │   DoD         │   │   changes     │   │               │ │
│  +---------------+   +---------------+   +---------------+ │
│                              ▼                           │
│                        +---------------+                   │
│                        │    PLANNER    │                  │
│                        │  Evaluates:   │                  │
│                        │  DoD met?     │                  │
│                        │  Yes → done   │                  │
│                        │  No → next    │                  │
│                        │        iteration              │
│                        +---------------+                   │
└──────────────────────────────────────────────────────────┘
```

### Key concepts

- **Step** — One agent invocation (e.g., planner plan, coder code, tester test)
- **Iteration** — One full pass through planner → coder → tester → planner evaluate
- **Sequential** — Roles run one at a time, never in parallel
- **Shared worktree** — All roles use the same git branch; commits are the handoff mechanism
- **CHANGELOG.md** — Auto-generated in the worktree; every appends step history for context
- **Human-in-the-loop** — Any role can pause and ask questions; frontend shows persistent input panel
- **Override** — User can interject at any time via the Active Step Panel chat input
- **Max iterations** — Default is 5; the Planner decides `continue`/`done` after each evaluate step

---

## Common Issues

### "Cannot reach Ollama at ..."

The backend cannot connect to Ollama. Check:
1. `OLLAMA_ENDPOINT` in `.env` is correct
2. Your API key is set in `OLLAMA_API`
3. If using Ollama Cloud, the endpoint should be `https://ollama.com` (not `https://api.ollama.cloud`)

### Agents show "localhost:11435" as endpoint

The default agents were seeded with `http://localhost:11435`. To use Ollama Cloud:
1. Go to **Agent Library**
2. Edit each agent
3. Set **Ollama Endpoint** to `https://ollama.com`
4. Set **API Key** to your key
5. Click **Save**

Or run this curl to bulk-update:

```bash
API_KEY="your-key"
ENDPOINT="https://ollama.com"

for id in 1 2 3; do
  curl -s -X PUT http://localhost:8002/api/agents/$id \
    -H "Content-Type: application/json" \
    -d "{\"ollama_endpoint\":\"$ENDPOINT\",\"api_key\":\"$API_KEY\"}"
done
```

### "No such file or directory" when agents try to write files

1. Check `PROJECT_DIR` in `.env` points to a real directory
2. Restart with `docker compose up -d`
3. Check **Settings** → **Working Directory** is `/workspace`

### Frontend shows loading spinner forever

This was a caching bug that has been fixed. If you see it:
1. Hard refresh the browser (`Ctrl+Shift+R` or `Cmd+Shift+R`)
2. Check the browser console for errors
3. Verify the backend is healthy: `curl http://localhost:8002/api/health`

---

## Next Steps

- **Customize agents** — Edit system prompts, temperature, or swap models
- **Create jobs** — Assign different agent combinations to different tasks
- **Set Definition of Done** — Each job's top-level DoD guides the pipeline
- **Review runs** — Check the History panel for step-by-step output
- **Read the project state** — See `docs/PROJECT-STATE-2026-04-29.md` for detailed architecture
- **Read the changelog** — See `docs/CHANGELOG-2026-04-29.md` for complete list of changes

---

## Manual Setup (No Docker)

If you prefer not to use Docker:

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env.local`.
