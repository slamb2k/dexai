"""
WebSocket Server for Real-time Dashboard Updates

Provides real-time event streaming to connected dashboard clients:
- dex:state - Avatar state changes
- activity:new - New activity events
- task:update - Task status changes
- metrics:update - Metric updates

Usage:
    Connect to ws://localhost:8080/ws
    Events are broadcast to all connected clients as JSON messages.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Set, Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.

    Handles:
    - Connection lifecycle (connect, disconnect)
    - Message broadcasting to all clients
    - Ping/pong for connection health
    - Batching for high-frequency events
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._broadcast_queue: List[Dict] = []
        self._broadcast_task: Optional[asyncio.Task] = None
        self._batch_interval_ms: int = 100

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

        # Send initial state
        await self._send_initial_state(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def _send_initial_state(self, websocket: WebSocket):
        """Send current state to newly connected client."""
        try:
            from tools.dashboard.backend.database import get_dex_state, get_quick_stats

            # Send current Dex state
            state = get_dex_state()
            await websocket.send_json({
                "event": "dex:state",
                "data": {
                    "state": state.get('state', 'idle'),
                    "task": state.get('current_task'),
                    "previous_state": None
                },
                "timestamp": datetime.now().isoformat()
            })

            # Send current metrics summary
            stats = get_quick_stats()
            await websocket.send_json({
                "event": "metrics:update",
                "data": stats,
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Error sending initial state: {e}")

    async def broadcast(self, message: Dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        # Ensure message has required fields
        if 'timestamp' not in message:
            message['timestamp'] = datetime.now().isoformat()

        message_json = json.dumps(message, default=str)

        # Send to all connections, removing dead ones
        dead_connections = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.debug(f"Failed to send to client: {e}")
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections.discard(conn)

    async def broadcast_batched(self, message: Dict):
        """
        Queue a message for batched broadcast.

        Messages are collected for batch_interval_ms then sent together.
        Useful for high-frequency events.
        """
        self._broadcast_queue.append(message)

        # Start batch task if not running
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self._process_batch())

    async def _process_batch(self):
        """Process queued messages after delay."""
        await asyncio.sleep(self._batch_interval_ms / 1000)

        if not self._broadcast_queue:
            return

        # Collect all queued messages
        messages = self._broadcast_queue.copy()
        self._broadcast_queue.clear()

        # Send as batch
        await self.broadcast({
            "event": "batch",
            "data": messages,
            "timestamp": datetime.now().isoformat()
        })


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time updates.

    Clients can connect with an optional token query parameter for authentication.
    After connection, the server will push events as they occur.

    Events:
    - dex:state: Avatar state changes
    - activity:new: New activity events
    - task:update: Task status changes
    - metrics:update: Periodic metrics updates
    - batch: Multiple events batched together
    """
    # Optional: Validate token if authentication is required
    # For now, we allow all connections

    await manager.connect(websocket)

    try:
        while True:
            # Keep connection alive, handle incoming messages
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # Ping interval
                )

                # Handle client messages (e.g., ping)
                try:
                    message = json.loads(data)
                    if message.get('event') == 'ping':
                        await websocket.send_json({
                            "event": "pong",
                            "timestamp": datetime.now().isoformat()
                        })
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_json({
                        "event": "ping",
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception:
                    break

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# =============================================================================
# Broadcast Functions (called by other parts of the application)
# =============================================================================

async def broadcast_state_change(
    state: str,
    task: Optional[str] = None,
    previous_state: Optional[str] = None
):
    """
    Broadcast Dex state change to all connected clients.

    Args:
        state: New avatar state
        task: Current task description (optional)
        previous_state: Previous state (optional)
    """
    await manager.broadcast({
        "event": "dex:state",
        "data": {
            "state": state,
            "task": task,
            "previous_state": previous_state
        }
    })


async def broadcast_activity(event_data: Dict):
    """
    Broadcast new activity event to all connected clients.

    Args:
        event_data: Activity event dictionary
    """
    await manager.broadcast({
        "event": "activity:new",
        "data": event_data
    })


async def broadcast_task_update(task_data: Dict):
    """
    Broadcast task status update to all connected clients.

    Args:
        task_data: Task data dictionary with id, status, etc.
    """
    await manager.broadcast({
        "event": "task:update",
        "data": task_data
    })


async def broadcast_metrics_update(metrics_data: Optional[Dict] = None):
    """
    Broadcast metrics update to all connected clients.

    If no metrics_data provided, fetches current quick stats.
    """
    if metrics_data is None:
        try:
            from tools.dashboard.backend.database import get_quick_stats
            metrics_data = get_quick_stats()
        except Exception:
            metrics_data = {}

    await manager.broadcast({
        "event": "metrics:update",
        "data": metrics_data
    })


# =============================================================================
# Sync Broadcast Functions (for non-async contexts)
# =============================================================================

def sync_broadcast_state_change(
    state: str,
    task: Optional[str] = None,
    previous_state: Optional[str] = None
):
    """
    Synchronous wrapper for broadcasting state changes.

    Use this from synchronous code (e.g., CLI scripts).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast_state_change(state, task, previous_state))
        else:
            loop.run_until_complete(broadcast_state_change(state, task, previous_state))
    except Exception as e:
        logger.debug(f"Could not broadcast state change: {e}")


def sync_broadcast_activity(event_data: Dict):
    """Synchronous wrapper for broadcasting activity events."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast_activity(event_data))
        else:
            loop.run_until_complete(broadcast_activity(event_data))
    except Exception as e:
        logger.debug(f"Could not broadcast activity: {e}")


# Export router and manager
ws_router = router
__all__ = [
    'ws_router',
    'manager',
    'broadcast_state_change',
    'broadcast_activity',
    'broadcast_task_update',
    'broadcast_metrics_update',
    'sync_broadcast_state_change',
    'sync_broadcast_activity'
]
