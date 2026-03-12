"""WebSocket handlers for live status and log streaming.

Two WebSocket endpoints:
- /ws/status — live system-status updates
- /ws/logs — live activity log stream

Each connected client is registered in a broadcast set.
Status events from Service Bus (or internal polling) are forwarded to all
connected clients in real-time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from opentelemetry import trace

from .models import WSMessage

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class ConnectionManager:
    """Manages a set of active WebSocket connections for a single channel."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WS %s: client connected (%d total)", self.name, len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WS %s: client disconnected (%d total)", self.name, len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected clients. Drops broken connections."""
        dead: list[WebSocket] = []
        payload = json.dumps(message, default=str)
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Global managers
status_manager = ConnectionManager("status")
log_manager = ConnectionManager("logs")


# ── WebSocket endpoint handlers ────────────────────────────────────────────


async def ws_status_handler(websocket: WebSocket) -> None:
    """Handle a single WebSocket connection on /ws/status."""
    await status_manager.connect(websocket)
    try:
        # Send initial status
        await websocket.send_json(
            WSMessage(
                type="connected",
                data={"channel": "status", "message": "Connected to status stream"},
            ).model_dump(mode="json")
        )
        # Keep connection alive; listen for client pings
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_json(
                        WSMessage(type="pong", data={}).model_dump(mode="json")
                    )
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json(
                    WSMessage(
                        type="heartbeat",
                        data={"timestamp": datetime.now(timezone.utc).isoformat()},
                    ).model_dump(mode="json")
                )
    except WebSocketDisconnect:
        status_manager.disconnect(websocket)
    except Exception:
        logger.exception("WS status handler error")
        status_manager.disconnect(websocket)


async def ws_logs_handler(websocket: WebSocket) -> None:
    """Handle a single WebSocket connection on /ws/logs."""
    await log_manager.connect(websocket)
    try:
        await websocket.send_json(
            WSMessage(
                type="connected",
                data={"channel": "logs", "message": "Connected to log stream"},
            ).model_dump(mode="json")
        )
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_json(
                        WSMessage(type="pong", data={}).model_dump(mode="json")
                    )
            except asyncio.TimeoutError:
                await websocket.send_json(
                    WSMessage(
                        type="heartbeat",
                        data={"timestamp": datetime.now(timezone.utc).isoformat()},
                    ).model_dump(mode="json")
                )
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)
    except Exception:
        logger.exception("WS logs handler error")
        log_manager.disconnect(websocket)


# ── Broadcast helpers (called from Service Bus or internal events) ─────────


async def broadcast_status(event: dict[str, Any]) -> None:
    """Broadcast a status event to all status WebSocket clients."""
    msg = WSMessage(type="status_update", data=event)
    await status_manager.broadcast(msg.model_dump(mode="json"))


async def broadcast_log(entry: dict[str, Any]) -> None:
    """Broadcast a log entry to all log WebSocket clients."""
    msg = WSMessage(type="log_entry", data=entry)
    await log_manager.broadcast(msg.model_dump(mode="json"))
