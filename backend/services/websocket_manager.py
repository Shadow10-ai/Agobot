"""WebSocket connection manager — singleton used by bot_loop to broadcast live updates."""
import logging
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)
        logger.debug(f"WS client connected. Total: {len(self.connections)}")

    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)
        logger.debug(f"WS client disconnected. Total: {len(self.connections)}")

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected clients. Dead connections are silently pruned."""
        if not self.connections:
            return
        dead = set()
        for ws in list(self.connections):
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.connections -= dead


# Module-level singleton — imported by bot_loop and ws_routes
ws_manager = WebSocketManager()
