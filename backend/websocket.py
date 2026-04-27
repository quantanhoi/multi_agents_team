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
