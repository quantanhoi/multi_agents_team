from fastapi import APIRouter, HTTPException, BackgroundTasks
from pathlib import Path
from typing import Optional, List
import json
import aiosqlite
from database import DB_PATH
from models import RunStart, RunResponse, HumanResponse, StepOut
from orchestrator import Orchestrator
from websocket import ws_manager
from opencode_agent import OpenCodeAgentError

router = APIRouter(prefix="/api/runs", tags=["runs"])

def _db_to_run(row) -> dict:
    if not row:
        return None
    d = dict(row)
    d["context"] = json.loads(d.get("context", "{}"))
    d["coder_outputs"] = json.loads(d.get("coder_outputs", "[]"))
    d["test_reports"] = json.loads(d.get("test_reports", "[]"))
    d["human_requests"] = json.loads(d.get("human_requests", "[]"))
    d["roadmap"] = json.loads(d["roadmap"]) if d.get("roadmap") else None
    return d

@router.post("", response_model=RunResponse, status_code=201)
async def start_run(data: RunStart, background_tasks: BackgroundTasks):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        job = await (await db.execute("SELECT * FROM jobs WHERE id = ?", (data.job_id,))).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")

        cursor = await db.execute(
            "INSERT INTO runs (job_id, status, feature_request, context) VALUES (?, 'pending', ?, ?)",
            (data.job_id, data.feature_request, json.dumps(data.context.model_dump()))
        )
        await db.commit()
        run_id = cursor.lastrowid

        orchestrator = Orchestrator(run_id, dict(job))
        background_tasks.add_task(orchestrator.run, data.feature_request, data.context.model_dump())

        row = await (await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))).fetchone()
        return _db_to_run(row)
    finally:
        await db.close()

@router.get("", response_model=List[RunResponse])
async def list_runs(job_id: Optional[int] = None, status: Optional[str] = None):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
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
        return [_db_to_run(r) for r in rows]
    finally:
        await db.close()

@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: int):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        row = await (await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        return _db_to_run(row)
    finally:
        await db.close()

@router.post("/{run_id}/resume")
async def resume_run(run_id: int, response: HumanResponse):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        row = await (await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        requests = json.loads(row["human_requests"] or "[]")
        if not requests or requests[-1].get("response"):
            raise HTTPException(400, "No pending human input request")

        requests[-1]["response"] = response.model_dump()
        previous_status = requests[-1].get("previous_status", "planning_draft")
        await db.execute(
            "UPDATE runs SET human_requests = ?, status = ? WHERE id = ?",
            (json.dumps(requests), previous_status, run_id)
        )
        await db.commit()
        ws_manager.signal_human_input(run_id)
        return {"status": "resumed"}
    finally:
        await db.close()

@router.post("/{run_id}/stop")
async def stop_run(run_id: int):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("UPDATE runs SET status = 'failed', completed_at = datetime('now') WHERE id = ?", (run_id,))
        await db.commit()
        return {"status": "stopped"}
    finally:
        await db.close()

@router.get("/{run_id}/steps", response_model=List[StepOut])
async def get_run_steps(run_id: int):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        cursor = await db.execute(
            "SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_number",
            (run_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()

@router.get("/{run_id}/changelog")
async def get_run_changelog(run_id: int):
    worktree_path = Path(".") / ".worktrees" / f"run-{run_id}"
    changelog = worktree_path / "CHANGELOG.md"
    if changelog.exists():
        return {"content": changelog.read_text()}
    return {"content": ""}
