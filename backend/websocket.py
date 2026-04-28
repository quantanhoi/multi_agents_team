import json
import asyncio
from fastapi import WebSocket
from typing import Dict

class WSManager:
    def __init__(self):
        self._connections: Dict[int, WebSocket] = {}
        self._human_input_events: Dict[int, asyncio.Event] = {}

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

    def get_human_input_event(self, run_id: int) -> asyncio.Event:
        if run_id not in self._human_input_events:
            self._human_input_events[run_id] = asyncio.Event()
        return self._human_input_events[run_id]

    def signal_human_input(self, run_id: int):
        event = self._human_input_events.get(run_id)
        if event:
            event.set()

    def clear_human_input_event(self, run_id: int):
        self._human_input_events.pop(run_id, None)

ws_manager = WSManager()
