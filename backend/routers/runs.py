from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional, List
import json
from database import DB_PATH, get_db
from models import RunStart, RunResponse, HumanResponse
from orchestrator import Orchestrator
import aiosqlite

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
    db = await anext(get_db())
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
        return [_db_to_run(r) for r in rows]
    finally:
        await db.close()

@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: int):
    db = await anext(get_db())
    try:
        row = await (await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        return _db_to_run(row)
    finally:
        await db.close()

@router.post("/{run_id}/resume")
async def resume_run(run_id: int, response: HumanResponse):
    db = await anext(get_db())
    try:
        row = await (await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        requests = json.loads(row["human_requests"] or "[]")
        if not requests or requests[-1].get("response"):
            raise HTTPException(400, "No pending human input request")

        requests[-1]["response"] = response.model_dump()
        # Restore previous status so orchestrator loop resumes
        # The orchestrator poll loop will see status changed and continue
        await db.execute(
            "UPDATE runs SET human_requests = ?, status = 'coding' WHERE id = ?",
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
