from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Multi-Agent Studio", lifespan=lifespan)

from routers.agents import router as agents_router
from routers.jobs import router as jobs_router
from routers.settings import router as settings_router
app.include_router(agents_router)
app.include_router(jobs_router)
app.include_router(settings_router)

from websocket import ws_manager

@app.websocket("/ws/runs/{run_id}")
async def ws_endpoint(ws: WebSocket, run_id: int):
    await ws_manager.connect(run_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id)

from routers.runs import router as runs_router
app.include_router(runs_router)

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
