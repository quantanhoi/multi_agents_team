import json
from fastapi import APIRouter, HTTPException
from typing import List
import aiosqlite
from database import DB_PATH
from models import JobCreate, JobUpdate, JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("", response_model=List[JobResponse])
async def list_jobs():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        rows = await db.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        jobs = await rows.fetchall()
        results = []
        for j in jobs:
            d = dict(j)
            d["agent_overrides"] = json.loads(d.get("agent_overrides", "{}"))
            results.append(d)
        return results
    finally:
        await db.close()

@router.post("", response_model=JobResponse, status_code=201)
async def create_job(job: JobCreate):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        for role, agent_id in [("planner", job.planner_agent_id), ("coder", job.coder_agent_id), ("tester", job.tester_agent_id)]:
            exists = await (await db.execute("SELECT id FROM agents WHERE id = ? AND role = ?", (agent_id, role))).fetchone()
            if not exists:
                raise HTTPException(400, f"Agent {agent_id} not found or not a {role}")

        cursor = await db.execute(
            "INSERT INTO jobs (name, description, planner_agent_id, coder_agent_id, tester_agent_id, agent_overrides, loop_mode, max_iterations) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job.name, job.description, job.planner_agent_id, job.coder_agent_id, job.tester_agent_id, json.dumps(job.agent_overrides), job.loop_mode, job.max_iterations)
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,))).fetchone()
        d = dict(row)
        d["agent_overrides"] = json.loads(d.get("agent_overrides", "{}"))
        return d
    finally:
        await db.close()

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        row = await (await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        d = dict(row)
        d["agent_overrides"] = json.loads(d.get("agent_overrides", "{}"))
        return d
    finally:
        await db.close()

@router.put("/{job_id}", response_model=JobResponse)
async def update_job(job_id: int, updates: JobUpdate):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        existing = await (await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))).fetchone()
        if not existing:
            raise HTTPException(404, "Job not found")

        fields = {k: v for k, v in updates.model_dump().items() if v is not None}
        if "agent_overrides" in fields:
            fields["agent_overrides"] = json.dumps(fields["agent_overrides"])
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            set_clause += ", updated_at = datetime('now')"
            await db.execute(
                f"UPDATE jobs SET {set_clause} WHERE id = ?",
                (*fields.values(), job_id)
            )
            await db.commit()

        row = await (await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))).fetchone()
        d = dict(row)
        d["agent_overrides"] = json.loads(d.get("agent_overrides", "{}"))
        return d
    finally:
        await db.close()

@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: int):
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        existing = await (await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))).fetchone()
        if not existing:
            raise HTTPException(404, "Job not found")
        await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        await db.commit()
    finally:
        await db.close()
