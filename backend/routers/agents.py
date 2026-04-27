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
