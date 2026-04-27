# Multi-Agent LLM Orchestration System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a multi-agent LLM orchestration system with a React UI for configuring agents and jobs, triggering runs, and reviewing results.

**Architecture:** FastAPI backend + React SPA frontend + SQLite. Backend runs async orchestrator that coordinates 3 Ollama cloud models (Planner/Coder/Tester) through a planning-review-then-execute loop with human-input support.

**Tech Stack:** Python 3.12+, FastAPI, SQLite (aiosqlite), httpx (async Ollama calls), React 18, TypeScript, Vite, React Router, TanStack Query

**Spec:** `docs/superpowers/specs/2026-04-27-multi-agent-orchestration-design.md`

---

### Task 1: Backend project scaffold + database + config

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/database.py`
- Create: `backend/config.py`
- Create: `backend/models.py`
- Create: `backend/main.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
aiosqlite==0.20.0
httpx==0.27.0
```

- [ ] **Step 2: Create database.py with SQLite setup**

```python
import aiosqlite

DB_PATH = "data/app.db"

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def init_db():
    import os
    os.makedirs("data", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('planner','coder','tester')),
            model_name TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            temperature REAL DEFAULT 0.3,
            ollama_endpoint TEXT DEFAULT 'http://localhost:11434',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            planner_agent_id INTEGER REFERENCES agents(id),
            coder_agent_id INTEGER REFERENCES agents(id),
            tester_agent_id INTEGER REFERENCES agents(id),
            agent_overrides TEXT DEFAULT '{}',
            loop_mode TEXT DEFAULT 'automatic' CHECK(loop_mode IN ('automatic','manual')),
            max_iterations INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES jobs(id),
            status TEXT DEFAULT 'pending',
            feature_request TEXT NOT NULL,
            context TEXT DEFAULT '{}',
            iterations INTEGER DEFAULT 0,
            roadmap TEXT DEFAULT NULL,
            coder_outputs TEXT DEFAULT '[]',
            test_reports TEXT DEFAULT '[]',
            human_requests TEXT DEFAULT '[]',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR IGNORE INTO settings (key, value) VALUES ('working_dir', '');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('ollama_endpoint', 'http://localhost:11434');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('default_temperature', '0.3');
    """)
    await db.commit()
    await db.close()
```

- [ ] **Step 3: Create config.py**

```python
import json
import aiosqlite
from database import DB_PATH

async def get_setting(key: str, default: str = "") -> str:
    db = await aiosqlite.connect(DB_PATH)
    row = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = await row.fetchone()
    await db.close()
    return result["value"] if result else default

async def set_setting(key: str, value: str):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value)
    )
    await db.commit()
    await db.close()
```

- [ ] **Step 4: Create models.py with all Pydantic schemas**

```python
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class AgentRole(str, Enum):
    planner = "planner"
    coder = "coder"
    tester = "tester"

class AgentCreate(BaseModel):
    name: str
    role: AgentRole
    model_name: str
    system_prompt: str
    temperature: float = 0.3
    ollama_endpoint: str = "http://localhost:11434"

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    model_name: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    ollama_endpoint: Optional[str] = None

class AgentResponse(BaseModel):
    id: int
    name: str
    role: str
    model_name: str
    system_prompt: str
    temperature: float
    ollama_endpoint: str
    created_at: str
    updated_at: str

class AgentOverride(BaseModel):
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    system_prompt_append: Optional[str] = None

class JobCreate(BaseModel):
    name: str
    description: str = ""
    planner_agent_id: int
    coder_agent_id: int
    tester_agent_id: int
    agent_overrides: dict = {}
    loop_mode: str = "automatic"
    max_iterations: int = 5

class JobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    planner_agent_id: Optional[int] = None
    coder_agent_id: Optional[int] = None
    tester_agent_id: Optional[int] = None
    agent_overrides: Optional[dict] = None
    loop_mode: Optional[str] = None
    max_iterations: Optional[int] = None

class JobResponse(BaseModel):
    id: int
    name: str
    description: str
    planner_agent_id: int
    coder_agent_id: int
    tester_agent_id: int
    agent_overrides: dict
    loop_mode: str
    max_iterations: int
    created_at: str
    updated_at: str

class RunContext(BaseModel):
    selected_files: List[str] = []
    known_bugs: List[str] = []
    constraints: List[str] = []
    extra_notes: str = ""

class RunStart(BaseModel):
    job_id: int
    feature_request: str
    context: RunContext = RunContext()

class HumanResponse(BaseModel):
    response_text: str = ""
    uploaded_files: List[str] = []

class RunResponse(BaseModel):
    id: int
    job_id: int
    status: str
    feature_request: str
    context: dict
    iterations: int
    roadmap: Optional[dict] = None
    coder_outputs: list = []
    test_reports: list = []
    human_requests: list = []
    started_at: str
    completed_at: Optional[str] = None

class SettingsResponse(BaseModel):
    working_dir: str
    ollama_endpoint: str
    default_temperature: float

class SettingsUpdate(BaseModel):
    working_dir: Optional[str] = None
    ollama_endpoint: Optional[str] = None
    default_temperature: Optional[float] = None
```

- [ ] **Step 5: Create minimal main.py**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Multi-Agent Studio", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Verify startup**

Run: `cd backend && pip install -r requirements.txt && uvicorn main:app --reload`
Expected: health check at http://localhost:8000/api/health returns `{"status":"ok"}`

- [ ] **Step 7: Commit**

---

### Task 2: Backend Agent CRUD

**Files:**
- Create: `backend/routers/agents.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create agents router**

```python
from fastapi import APIRouter, HTTPException
from typing import List
from database import get_db
from models import AgentCreate, AgentUpdate, AgentResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])

@router.get("", response_model=List[AgentResponse])
async def list_agents():
    db = await anext(get_db())
    try:
        rows = await db.execute("SELECT * FROM agents ORDER BY created_at DESC")
        agents = await rows.fetchall()
        return [dict(a) for a in agents]
    finally:
        await db.close()

@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(agent: AgentCreate):
    db = await anext(get_db())
    try:
        cursor = await db.execute(
            "INSERT INTO agents (name, role, model_name, system_prompt, temperature, ollama_endpoint) VALUES (?, ?, ?, ?, ?, ?)",
            (agent.name, agent.role.value, agent.model_name, agent.system_prompt, agent.temperature, agent.ollama_endpoint)
        )
        await db.commit()
        row = await db.execute("SELECT * FROM agents WHERE id = ?", (cursor.lastrowid,))
        return dict(await (await row).fetchone())
    finally:
        await db.close()

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: int):
    db = await anext(get_db())
    try:
        row = await db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        agent = await row.fetchone()
        if not agent:
            raise HTTPException(404, "Agent not found")
        return dict(agent)
    finally:
        await db.close()

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: int, updates: AgentUpdate):
    db = await anext(get_db())
    try:
        existing = await (await db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))).fetchone()
        if not existing:
            raise HTTPException(404, "Agent not found")

        fields = {k: v for k, v in updates.model_dump().items() if v is not None}
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            set_clause += ", updated_at = datetime('now')"
            await db.execute(
                f"UPDATE agents SET {set_clause} WHERE id = ?",
                (*fields.values(), agent_id)
            )
            await db.commit()

        row = await (await db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))).fetchone()
        return dict(row)
    finally:
        await db.close()

@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: int):
    db = await anext(get_db())
    try:
        existing = await (await db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))).fetchone()
        if not existing:
            raise HTTPException(404, "Agent not found")
        await db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        await db.commit()
    finally:
        await db.close()
```

- [ ] **Step 2: Register router in main.py**

In `backend/main.py`, add after `app = FastAPI(...)`:
```python
from routers.agents import router as agents_router
app.include_router(agents_router)
```

- [ ] **Step 3: Test CRUD**

```bash
# Create
curl -X POST http://localhost:8000/api/agents \
  -H "Content-Type: application/json" \
  -d '{"name":"Kimi Planner","role":"planner","model_name":"kimi-k2.6","system_prompt":"You are the planner. Return JSON only.","temperature":0.3}'

# List
curl http://localhost:8000/api/agents

# Get
curl http://localhost:8000/api/agents/1

# Update
curl -X PUT http://localhost:8000/api/agents/1 \
  -H "Content-Type: application/json" \
  -d '{"temperature":0.2}'

# Delete
curl -X DELETE http://localhost:8000/api/agents/1
```

- [ ] **Step 4: Commit**

---

### Task 3: Backend Jobs + Settings CRUD

**Files:**
- Create: `backend/routers/jobs.py`
- Create: `backend/routers/settings.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create jobs router** (same pattern as agents, adapt for jobs table + models)

Follow the agent CRUD pattern from Task 2, replacing:
- Table: `jobs`
- Model classes: `JobCreate`, `JobUpdate`, `JobResponse`
- `agent_overrides` is stored as JSON string: `json.dumps(data)` on write, `json.loads(row["agent_overrides"])` on read
- `loop_mode` must be `"automatic"` or `"manual"`
- Validate that planner/coder/tester agent IDs exist

- [ ] **Step 2: Create settings router**

```python
from fastapi import APIRouter
from config import get_setting, set_setting
from models import SettingsResponse, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

@router.get("", response_model=SettingsResponse)
async def get_settings():
    return SettingsResponse(
        working_dir=await get_setting("working_dir"),
        ollama_endpoint=await get_setting("ollama_endpoint", "http://localhost:11434"),
        default_temperature=float(await get_setting("default_temperature", "0.3"))
    )

@router.put("", response_model=SettingsResponse)
async def update_settings(updates: SettingsUpdate):
    data = updates.model_dump()
    for key, value in data.items():
        if value is not None:
            await set_setting(key, str(value))
    return await get_settings()
```

- [ ] **Step 3: Register both routers in main.py**

```python
from routers.jobs import router as jobs_router
from routers.settings import router as settings_router
app.include_router(jobs_router)
app.include_router(settings_router)
```

- [ ] **Step 4: Test jobs + settings via curl**

- [ ] **Step 5: Commit**

---

### Task 4: WebSocket manager + Ollama client

**Files:**
- Create: `backend/websocket.py`
- Create: `backend/ollama_client.py`

- [ ] **Step 1: Create websocket.py**

```python
import json
from fastapi import WebSocket
from typing import Dict

class WSManager:
    def __init__(self):
        self._connections: Dict[int, WebSocket] = {}

    async def connect(self, run_id: int, ws: WebSocket):
        await ws.accept()
        self._connections[run_id] = ws

    def disconnect(self, run_id: int):
        self._connections.pop(run_id, None)

    async def send(self, run_id: int, event: dict):
        ws = self._connections.get(run_id)
        if ws:
            try:
                await ws.send_json(event)
            except Exception:
                self.disconnect(run_id)

ws_manager = WSManager()
```

- [ ] **Step 2: Create ollama_client.py**

```python
import json
import httpx
from typing import Dict

class OllamaError(Exception):
    pass

async def call_ollama(endpoint: str, model: str, messages: list, temperature: float = 0.3, max_retries: int = 2) -> dict:
    url = f"{endpoint}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature}
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
                return json.loads(content)
        except json.JSONDecodeError as e:
            last_error = e
            # Feed parse error back for correction (one retry)
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"Your response was not valid JSON. Error: {e}. Please return valid JSON only."})
            if attempt == max_retries:
                raise OllamaError(f"Failed to parse JSON after {max_retries} retries: {e}")
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            last_error = e
            if attempt == max_retries:
                raise OllamaError(f"Ollama API error after {max_retries} retries: {e}")
    raise OllamaError(f"Unexpected error: {last_error}")
```

- [ ] **Step 3: Commit**

---

### Task 5: Orchestrator engine

**Files:**
- Create: `backend/orchestrator.py`

- [ ] **Step 1: Create orchestrator.py with full loop**

```python
import json
import os
import subprocess
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

            await self._update_status("planning_finalize")
            result = await self._execution_loop(roadmap)

            await self._update_status("done")
            await self._broadcast({"type": "done", "status": "done", "summary": "All phases complete", "roadmap": result})
            return result
        except OllamaError as e:
            await self._update_status("failed")
            await self._broadcast({"type": "failed", "status": "failed", "message": str(e)})
            raise
        except Exception as e:
            await self._update_status("failed")
            await self._broadcast({"type": "error", "phase": "...", "message": str(e), "retryable": False})
            raise

    async def _planning_phase(self, feature_request: str, context: dict):
        # 1a. Planner drafts
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

        # 1b. Coder reviews
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

        # 1c. Tester reviews
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

        # 1d. Planner finalizes
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

            # Coder
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

            # Tester
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

            # Planner re-evaluate
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
        prev_status = (await (await db.execute("SELECT status FROM runs WHERE id = ?", (self.run_id,))).fetchone())["status"]
        await db.execute("UPDATE runs SET status = 'waiting_for_human' WHERE id = ?", (self.run_id,))
        await db.commit()
        await db.close()

        await ws_manager.send(self.run_id, {
            "type": "human_input_required",
            "requested_by": req["requested_by"],
            "message": req["message"],
            "input_type": req.get("input_type", "text")
        })

        # Store request, will be resolved by resume endpoint
        db = await aiosqlite.connect(DB_PATH)
        requests = json.loads((await (await db.execute("SELECT human_requests FROM runs WHERE id = ?", (self.run_id,))).fetchone())["human_requests"] or "[]")
        request_entry = {"request": req, "response": None, "timestamp": datetime.utcnow().isoformat()}
        requests.append(request_entry)
        await db.execute("UPDATE runs SET human_requests = ? WHERE id = ?", (json.dumps(requests), self.run_id))
        await db.commit()
        await db.close()

        # Poll for response (block until resume endpoint sets it)
        while True:
            await __import__("asyncio").sleep(1)
            db = await aiosqlite.connect(DB_PATH)
            status = (await (await db.execute("SELECT status FROM runs WHERE id = ?", (self.run_id,))).fetchone())["status"]
            requests = json.loads((await (await db.execute("SELECT human_requests FROM runs WHERE id = ?", (self.run_id,))).fetchone())["human_requests"] or "[]")
            await db.close()
            if status != "waiting_for_human" and requests[-1].get("response"):
                break

        response = requests[-1]["response"]
        output["_human_response"] = response
        return output

    def _write_files(self, coder_output: dict):
        working_dir = __import__("asyncio").run(self._get_setting("working_dir"))
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
```

- [ ] **Step 2: Commit**

---

### Task 6: Backend Run API + WebSocket endpoint

**Files:**
- Create: `backend/routers/runs.py`
- Modify: `backend/main.py` (add WS route + runs router)

- [ ] **Step 1: Create runs router with start/list/get/resume/stop**

Follow the existing router patterns. Key additions:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from models import RunStart, RunResponse, HumanResponse
from orchestrator import Orchestrator
from websocket import ws_manager
import json, aiosqlite
from database import DB_PATH, get_db

router = APIRouter(prefix="/api/runs", tags=["runs"])

@router.post("", response_model=RunResponse, status_code=201)
async def start_run(data: RunStart, background_tasks: BackgroundTasks):
    db = await anext(get_db())
    try:
        # Load job config
        job = await (await db.execute("SELECT * FROM jobs WHERE id = ?", (data.job_id,))).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")

        cursor = await db.execute(
            "INSERT INTO runs (job_id, status, feature_request, context) VALUES (?, 'pending', ?, ?)",
            (data.job_id, data.feature_request, json.dumps(data.context.model_dump()))
        )
        await db.commit()
        run_id = cursor.lastrowid

        # Start orchestrator in background
        orchestrator = Orchestrator(run_id, dict(job))
        background_tasks.add_task(orchestrator.run, data.feature_request, data.context.model_dump())

        row = await (await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))).fetchone()
        result = dict(row)
        result["context"] = json.loads(result.get("context", "{}"))
        result["coder_outputs"] = json.loads(result.get("coder_outputs", "[]"))
        result["test_reports"] = json.loads(result.get("test_reports", "[]"))
        result["human_requests"] = json.loads(result.get("human_requests", "[]"))
        result["roadmap"] = json.loads(result["roadmap"]) if result.get("roadmap") else None
        return result
    finally:
        await db.close()

@router.get("", response_model=list[RunResponse])
async def list_runs(job_id: int = None, status: str = None):
    db = await anext(get_db())
    try:
        query = "SELECT * FROM runs"
        params = []
        conditions = []
        if job_id:
            conditions.append("job_id = ?")
            params.append(job_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY started_at DESC LIMIT 50"
        rows = await (await db.execute(query, params)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["context"] = json.loads(d.get("context", "{}"))
            d["coder_outputs"] = json.loads(d.get("coder_outputs", "[]"))
            d["test_reports"] = json.loads(d.get("test_reports", "[]"))
            d["human_requests"] = json.loads(d.get("human_requests", "[]"))
            d["roadmap"] = json.loads(d["roadmap"]) if d.get("roadmap") else None
            results.append(d)
        return results
    finally:
        await db.close()

@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: int):
    # Same as list but single row, 404 if not found

@router.post("/{run_id}/resume")
async def resume_run(run_id: int, response: HumanResponse):
    db = await anext(get_db())
    try:
        row = await (await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        requests = json.loads(row["human_requests"] or "[]")
        if not requests:
            raise HTTPException(400, "No pending human input request")

        requests[-1]["response"] = response.model_dump()
        await db.execute(
            "UPDATE runs SET human_requests = ?, status = 'planning_draft' WHERE id = ?",
            (json.dumps(requests), run_id)
        )
        await db.commit()
        return {"status": "resumed"}
    finally:
        await db.close()

@router.post("/{run_id}/stop")
async def stop_run(run_id: int):
    db = await anext(get_db())
    try:
        await db.execute("UPDATE runs SET status = 'failed', completed_at = datetime('now') WHERE id = ?", (run_id,))
        await db.commit()
        return {"status": "stopped"}
    finally:
        await db.close()
```

- [ ] **Step 2: Add WebSocket endpoint in main.py**

```python
from fastapi import WebSocket, WebSocketDisconnect
from websocket import ws_manager

@app.websocket("/ws/runs/{run_id}")
async def ws_endpoint(ws: WebSocket, run_id: int):
    await ws_manager.connect(run_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep alive, ignore client messages
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id)
```

- [ ] **Step 3: Register runs router**

```python
from routers.runs import router as runs_router
app.include_router(runs_router)
```

- [ ] **Step 4: Test run lifecycle via curl**

- [ ] **Step 5: Commit**

---

### Task 7: Frontend project scaffold + types + API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Scaffold with Vite**

```bash
cd frontend && npm create vite@latest . -- --template react-ts
npm install react-router-dom @tanstack/react-query
```

- [ ] **Step 2: Create types.ts**

```typescript
export type AgentRole = 'planner' | 'coder' | 'tester';
export type RunStatus = 'pending' | 'planning_draft' | 'planning_review_coder' | 'planning_review_tester' | 'planning_finalize' | 'coding' | 'testing' | 'evaluating' | 'waiting_for_human' | 'done' | 'failed';

export interface Agent {
  id: number; name: string; role: AgentRole; model_name: string;
  system_prompt: string; temperature: number; ollama_endpoint: string;
  created_at: string; updated_at: string;
}

export interface AgentOverride {
  model_name?: string | null; temperature?: number | null; system_prompt_append?: string | null;
}

export interface Job {
  id: number; name: string; description: string;
  planner_agent_id: number; coder_agent_id: number; tester_agent_id: number;
  agent_overrides: { planner?: AgentOverride; coder?: AgentOverride; tester?: AgentOverride };
  loop_mode: 'automatic' | 'manual'; max_iterations: number;
  created_at: string; updated_at: string;
}

export interface RunContext {
  selected_files: string[]; known_bugs: string[]; constraints: string[]; extra_notes: string;
}

export interface Run {
  id: number; job_id: number; status: RunStatus; feature_request: string;
  context: RunContext; iterations: number; roadmap: any;
  coder_outputs: any[]; test_reports: any[]; human_requests: any[];
  started_at: string; completed_at: string | null;
}

export interface Settings {
  working_dir: string; ollama_endpoint: string; default_temperature: number;
}

export interface HumanInputRequest {
  message: string; input_type: 'text' | 'file_upload' | 'screenshot_upload'; requested_by: string;
}

export interface WSMessage {
  type: 'phase_change' | 'agent_output' | 'human_input_required' | 'done' | 'failed' | 'error';
  phase?: string; message?: string; agent?: string; output?: any;
  requested_by?: string; input_type?: string; status?: string; summary?: string;
  retryable?: boolean;
}
```

- [ ] **Step 3: Create api.ts**

```typescript
import { Agent, Job, Run, RunContext, Settings } from './types';

const BASE = 'http://localhost:8000';

async function req<T>(method: string, path: string, body?: any): Promise<T> {
  const opts: RequestInit = { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined };
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) throw new Error(`${method} ${path} failed: ${res.status}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  agents: {
    list: () => req<Agent[]>('GET', '/api/agents'),
    get: (id: number) => req<Agent>('GET', `/api/agents/${id}`),
    create: (data: Partial<Agent>) => req<Agent>('POST', '/api/agents', data),
    update: (id: number, data: Partial<Agent>) => req<Agent>('PUT', `/api/agents/${id}`, data),
    delete: (id: number) => req<void>('DELETE', `/api/agents/${id}`),
  },
  jobs: {
    list: () => req<Job[]>('GET', '/api/jobs'),
    get: (id: number) => req<Job>('GET', `/api/jobs/${id}`),
    create: (data: Partial<Job>) => req<Job>('POST', '/api/jobs', data),
    update: (id: number, data: Partial<Job>) => req<Job>('PUT', `/api/jobs/${id}`, data),
    delete: (id: number) => req<void>('DELETE', `/api/jobs/${id}`),
  },
  runs: {
    start: (jobId: number, featureRequest: string, context: RunContext) =>
      req<Run>('POST', '/api/runs', { job_id: jobId, feature_request: featureRequest, context }),
    list: (jobId?: number, status?: string) => {
      const params = new URLSearchParams();
      if (jobId) params.set('job_id', String(jobId));
      if (status) params.set('status', status);
      return req<Run[]>('GET', `/api/runs?${params}`);
    },
    get: (id: number) => req<Run>('GET', `/api/runs/${id}`),
    resume: (id: number, response: { response_text: string; uploaded_files: string[] }) =>
      req<any>('POST', `/api/runs/${id}/resume`, response),
    stop: (id: number) => req<any>('POST', `/api/runs/${id}/stop`),
  },
  settings: {
    get: () => req<Settings>('GET', '/api/settings'),
    update: (data: Partial<Settings>) => req<Settings>('PUT', '/api/settings', data),
  },
};
```

- [ ] **Step 4: Create App.tsx with routing shell**

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { AgentsPage } from './pages/AgentsPage';
import { JobsPage } from './pages/JobsPage';
import { RunPage } from './pages/RunPage';
import { HistoryPage } from './pages/HistoryPage';
import { SettingsPage } from './pages/SettingsPage';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex h-screen">
          <Sidebar />
          <div className="flex-1 flex flex-col">
            <TopBar />
            <main className="flex-1 overflow-auto p-6">
              <Routes>
                <Route path="/" element={<RunPage />} />
                <Route path="/agents" element={<AgentsPage />} />
                <Route path="/jobs" element={<JobsPage />} />
                <Route path="/history" element={<HistoryPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 5: Create Sidebar.tsx and TopBar.tsx (minimal)**

Sidebar: nav links with `useLocation` to highlight active. TopBar: simple bar with app title.

- [ ] **Step 6: Verify frontend starts**

Run: `cd frontend && npm run dev`
Expected: App loads at http://localhost:5173 with sidebar nav

- [ ] **Step 7: Commit**

---

### Task 8: Frontend Agents + Jobs + Settings pages

**Files:**
- Create: `frontend/src/pages/AgentsPage.tsx`
- Create: `frontend/src/components/AgentForm.tsx`
- Create: `frontend/src/pages/JobsPage.tsx`
- Create: `frontend/src/components/JobForm.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Build AgentsPage** — list agents with TanStack Query `useQuery`, delete with `useMutation`, modal/drawer form for create/edit. Show role badge (color-coded), model name, truncated prompt. Delete with confirm dialog.

- [ ] **Step 2: Build AgentForm** — controlled form: name input, role select (planner/coder/tester), model_name input, system_prompt textarea, temperature number input (0-2 step 0.1). POST to create, PUT to update.

- [ ] **Step 3: Build JobsPage** — list jobs with TanStack Query. Each row shows: name, assigned agent names (fetched or joined), loop mode badge. Create/edit via modal form.

- [ ] **Step 4: Build JobForm** — name, description, 3 agent select dropdowns (populated from agent list), loop mode toggle (automatic/manual), max iterations number, expandable per-agent override section (model, temperature, extra prompt text).

- [ ] **Step 5: Build SettingsPage** — working_dir input, ollama_endpoint input, default_temperature number. Load with `useQuery`, save with `useMutation`. Success toast on save.

- [ ] **Step 6: Manual test all 3 pages**

- [ ] **Step 7: Commit**

---

### Task 9: Frontend Run Console page

**Files:**
- Create: `frontend/src/pages/RunPage.tsx`
- Create: `frontend/src/components/ContextBuilder.tsx`
- Create: `frontend/src/components/PhaseTimeline.tsx`
- Create: `frontend/src/components/OutputPanels.tsx`
- Create: `frontend/src/components/HumanInputModal.tsx`

- [ ] **Step 1: Build ContextBuilder** — job selector dropdown, feature request textarea, file picker placeholder (text input for file paths, comma-separated), known bugs textarea (one per line), constraints textarea (one per line), extra notes textarea, Run button. Validates: job selected + feature request non-empty.

- [ ] **Step 2: Build PhaseTimeline** — takes `currentPhase: RunStatus` and `completedPhases: RunStatus[]`. Renders horizontal pill trail: all lifecycle phases, green if completed, blue with pulse animation if current, gray outline if pending. If currentPhase is `waiting_for_human`, show yellow pill.

- [ ] **Step 3: Build OutputPanels** — 3 resizable panels (Plan | Coder Output | Test Report). Plan panel shows roadmap JSON pretty-printed. Coder panel shows latest coder_output with file diffs. Tester panel shows latest test_report with pass/fail badge and bug list. Each panel scrolls independently.

- [ ] **Step 4: Build HumanInputModal** — shown when `human_input_required` WS event received. Displays agent's message, text response input, file upload input. Submit calls `api.runs.resume()`. Modal closes on submit.

- [ ] **Step 5: Wire RunPage together** — state machine:
  - Idle: show ContextBuilder
  - Running: show PhaseTimeline + OutputPanels, connect WebSocket to `/ws/runs/{runId}`
  - WaitingForHuman: same as Running + HumanInputModal open
  - Done/Failed: show results, link to history

  WebSocket connection in `useEffect`:
  ```typescript
  useEffect(() => {
    if (!runId) return;
    const ws = new WebSocket(`ws://localhost:8000/ws/runs/${runId}`);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      // dispatch to state machine based on msg.type
    };
    return () => ws.close();
  }, [runId]);
  ```

- [ ] **Step 6: Manual test full run flow**

- [ ] **Step 7: Commit**

---

### Task 10: Frontend History page

**Files:**
- Create: `frontend/src/pages/HistoryPage.tsx`

- [ ] **Step 1: Build HistoryPage** — TanStack Query `useQuery` for `api.runs.list()`. Table: date, job name (resolve from job list), status badge, iterations, duration (completed_at - started_at). Click row to expand inline detail panel showing: roadmap phases with completion status, each iteration's coder output + test report, any human input exchanges. Link to re-run from history entry.

- [ ] **Step 2: Commit**

---

### Task 11: Seed default agents + end-to-end verification

- [ ] **Step 1: Create seed script** — `backend/seed.py` that creates 3 default agents (Kimi Planner, GLM Coder, DeepSeek Tester) and 1 default job using them.

- [ ] **Step 2: Full end-to-end test** — start backend + frontend, seed agents, create a job, trigger a run with a simple feature request, verify phases progress, check results in history.

- [ ] **Step 3: Commit**
