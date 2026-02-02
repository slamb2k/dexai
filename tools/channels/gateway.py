"""
Tool: WebSocket Gateway Server
Purpose: Real-time communication backbone for the messaging gateway

The gateway server provides:
- WebSocket connections for channel adapters
- Message routing between adapters and agents
- Health monitoring and metrics
- Graceful shutdown

Usage:
    python tools/channels/gateway.py --start
    python tools/channels/gateway.py --start --host 0.0.0.0 --port 18789
    python tools/channels/gateway.py --status
    python tools/channels/gateway.py --health

Dependencies (pip):
    - websockets>=12.0

Configuration:
    See args/channels.yaml for gateway settings
"""

import argparse
import asyncio
import json
import signal
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration defaults
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18789
DEFAULT_PING_INTERVAL = 30
DEFAULT_PING_TIMEOUT = 10
DEFAULT_MAX_MESSAGE_SIZE = 65536
DEFAULT_MAX_CONNECTIONS = 100
DEFAULT_SHUTDOWN_TIMEOUT = 30

# Status file for inter-process communication
STATUS_FILE = PROJECT_ROOT / ".tmp" / "gateway_status.json"


def load_config() -> dict[str, Any]:
    """Load gateway configuration from args/channels.yaml."""
    config_path = PROJECT_ROOT / "args" / "channels.yaml"
    defaults = {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "ping_interval": DEFAULT_PING_INTERVAL,
        "ping_timeout": DEFAULT_PING_TIMEOUT,
        "max_message_size": DEFAULT_MAX_MESSAGE_SIZE,
        "max_connections": DEFAULT_MAX_CONNECTIONS,
        "shutdown_timeout": DEFAULT_SHUTDOWN_TIMEOUT,
    }

    if not config_path.exists():
        return defaults

    try:
        import yaml

        with open(config_path) as f:
            config = yaml.safe_load(f)
        gateway_config = config.get("gateway", {})
        return {**defaults, **gateway_config}
    except ImportError:
        return defaults
    except Exception:
        return defaults


class GatewayServer:
    """
    WebSocket server for messaging gateway.

    Provides real-time bidirectional communication between:
    - Channel adapters (Telegram, Discord, Slack)
    - AI agent processing
    - Admin/monitoring clients
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        config: dict[str, Any] | None = None,
    ):
        self.host = host
        self.port = port
        self.config = config or load_config()

        # Import router
        from tools.channels.router import get_router

        self.router = get_router()

        # Connection tracking
        self.connections: dict[str, Any] = {}  # conn_id -> websocket
        self.subscriptions: dict[str, set[str]] = {}  # channel -> set of conn_ids

        # Server state
        self.running = False
        self.server = None
        self.start_time: datetime | None = None

        # Metrics
        self.metrics = {"messages_in": 0, "messages_out": 0, "connections_total": 0, "errors": 0}

    async def start(self) -> None:
        """Start the WebSocket server."""
        try:
            import websockets
        except ImportError:
            print("ERROR: websockets library required. Install with: pip install websockets")
            sys.exit(1)

        self.running = True
        self.start_time = datetime.now()

        # Write status file
        self._write_status()

        try:
            self.server = await websockets.serve(
                self.handle_connection,
                self.host,
                self.port,
                ping_interval=self.config.get("ping_interval", DEFAULT_PING_INTERVAL),
                ping_timeout=self.config.get("ping_timeout", DEFAULT_PING_TIMEOUT),
                max_size=self.config.get("max_message_size", DEFAULT_MAX_MESSAGE_SIZE),
            )

            # Log startup
            try:
                from tools.security import audit

                audit.log_event(
                    event_type="system",
                    action="gateway_started",
                    status="success",
                    details={"host": self.host, "port": self.port},
                )
            except Exception:
                pass

            print(f"Gateway server started on ws://{self.host}:{self.port}")

            # Wait for server to close
            await self.server.wait_closed()

        except OSError as e:
            if "Address already in use" in str(e):
                print(f"ERROR: Port {self.port} already in use")
            else:
                print(f"ERROR: {e}")
            sys.exit(1)

    async def stop(self) -> None:
        """Graceful shutdown."""
        print("Shutting down gateway...")
        self.running = False

        # Close all connections
        for conn_id, ws in list(self.connections.items()):
            try:
                await ws.close(1001, "Server shutting down")
            except Exception:
                pass

        # Close server
        if self.server:
            self.server.close()
            await asyncio.wait_for(
                self.server.wait_closed(),
                timeout=self.config.get("shutdown_timeout", DEFAULT_SHUTDOWN_TIMEOUT),
            )

        # Log shutdown
        try:
            from tools.security import audit

            audit.log_event(
                event_type="system",
                action="gateway_stopped",
                status="success",
                details={"uptime_seconds": self._get_uptime()},
            )
        except Exception:
            pass

        # Remove status file
        if STATUS_FILE.exists():
            STATUS_FILE.unlink()

        print("Gateway stopped")

    async def handle_connection(self, websocket) -> None:
        """
        Handle incoming WebSocket connection.

        Protocol:
        - Client sends JSON messages with 'type' field
        - Server responds with JSON messages
        - Supported types: ping, message, subscribe, unsubscribe
        """
        import websockets

        conn_id = str(uuid.uuid4())
        self.connections[conn_id] = websocket
        self.metrics["connections_total"] += 1

        client_info = {
            "id": conn_id,
            "remote": str(websocket.remote_address)
            if hasattr(websocket, "remote_address")
            else "unknown",
            "connected_at": datetime.now().isoformat(),
        }

        try:
            # Send welcome message
            await websocket.send(
                json.dumps(
                    {"type": "connected", "id": conn_id, "timestamp": datetime.now().isoformat()}
                )
            )

            async for raw_message in websocket:
                await self.handle_message(conn_id, websocket, raw_message)

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.metrics["errors"] += 1
            try:
                from tools.security import audit

                audit.log_event(
                    event_type="error",
                    action="connection_error",
                    details={"error": str(e), "conn_id": conn_id},
                )
            except Exception:
                pass
        finally:
            # Cleanup
            if conn_id in self.connections:
                del self.connections[conn_id]

            # Remove from all subscriptions
            for channel, subscribers in self.subscriptions.items():
                subscribers.discard(conn_id)

    async def handle_message(self, conn_id: str, ws, raw: str) -> None:
        """
        Process incoming WebSocket message.

        Message types:
        - ping: Health check (responds with pong)
        - message: Route through message pipeline
        - subscribe: Subscribe to receive outbound messages for a channel
        - unsubscribe: Unsubscribe from a channel
        - status: Get server status
        """
        try:
            data = json.loads(raw)
            msg_type = data.get("type")
            msg_id = data.get("id", str(uuid.uuid4()))

            if msg_type == "ping":
                await ws.send(
                    json.dumps(
                        {"type": "pong", "id": msg_id, "timestamp": datetime.now().isoformat()}
                    )
                )

            elif msg_type == "message":
                self.metrics["messages_in"] += 1

                # Parse payload into UnifiedMessage
                from tools.channels.models import UnifiedMessage

                payload = data.get("payload", {})
                message = UnifiedMessage.from_dict(payload)

                # Route through message pipeline
                result = await self.router.route_inbound(message)

                await ws.send(json.dumps({"type": "ack", "id": msg_id, "result": result}))

            elif msg_type == "subscribe":
                channel = data.get("payload", {}).get("channel")
                if channel:
                    if channel not in self.subscriptions:
                        self.subscriptions[channel] = set()
                    self.subscriptions[channel].add(conn_id)

                    await ws.send(
                        json.dumps({"type": "subscribed", "id": msg_id, "channel": channel})
                    )

            elif msg_type == "unsubscribe":
                channel = data.get("payload", {}).get("channel")
                if channel and channel in self.subscriptions:
                    self.subscriptions[channel].discard(conn_id)

                    await ws.send(
                        json.dumps({"type": "unsubscribed", "id": msg_id, "channel": channel})
                    )

            elif msg_type == "status":
                await ws.send(
                    json.dumps({"type": "status", "id": msg_id, "status": self.health_check()})
                )

            elif msg_type == "broadcast":
                # Send message to all subscribers of a channel
                channel = data.get("payload", {}).get("channel")
                content = data.get("payload", {}).get("content")

                if channel and content:
                    sent_count = await self.broadcast_to_channel(channel, content)
                    await ws.send(
                        json.dumps(
                            {"type": "broadcast_result", "id": msg_id, "sent_count": sent_count}
                        )
                    )

            else:
                await ws.send(
                    json.dumps(
                        {
                            "type": "error",
                            "id": msg_id,
                            "error": f"unknown_message_type: {msg_type}",
                        }
                    )
                )

        except json.JSONDecodeError:
            self.metrics["errors"] += 1
            await ws.send(json.dumps({"type": "error", "error": "invalid_json"}))
        except Exception as e:
            self.metrics["errors"] += 1
            await ws.send(json.dumps({"type": "error", "error": str(e)}))

    async def broadcast_to_channel(self, channel: str, content: dict[str, Any]) -> int:
        """
        Broadcast a message to all subscribers of a channel.

        Args:
            channel: Channel name
            content: Message content to broadcast

        Returns:
            Number of connections the message was sent to
        """
        subscribers = self.subscriptions.get(channel, set())
        sent_count = 0

        for conn_id in subscribers:
            ws = self.connections.get(conn_id)
            if ws:
                try:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "channel_message",
                                "channel": channel,
                                "content": content,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    )
                    sent_count += 1
                    self.metrics["messages_out"] += 1
                except Exception:
                    pass

        return sent_count

    def health_check(self) -> dict[str, Any]:
        """
        Return gateway health status.

        Returns:
            Dict with health information
        """
        uptime = self._get_uptime()

        return {
            "status": "healthy" if self.running else "stopped",
            "uptime_seconds": uptime,
            "host": self.host,
            "port": self.port,
            "connections": {
                "active": len(self.connections),
                "total": self.metrics["connections_total"],
            },
            "subscriptions": {
                channel: len(subscribers) for channel, subscribers in self.subscriptions.items()
            },
            "adapters": {name: {"status": "registered"} for name in self.router.adapters.keys()},
            "metrics": self.metrics,
        }

    def _get_uptime(self) -> int:
        """Get uptime in seconds."""
        if self.start_time:
            return int((datetime.now() - self.start_time).total_seconds())
        return 0

    def _write_status(self) -> None:
        """Write status file for inter-process communication."""
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        status = {
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "pid": None,  # Could add os.getpid() if needed
            "start_time": self.start_time.isoformat() if self.start_time else None,
        }
        try:
            import os

            status["pid"] = os.getpid()
        except Exception:
            pass

        with open(STATUS_FILE, "w") as f:
            json.dump(status, f)


def get_server_status() -> dict[str, Any]:
    """
    Get status of running gateway server.

    Returns:
        Dict with server status or error if not running
    """
    if not STATUS_FILE.exists():
        return {"running": False, "error": "Status file not found. Server may not be running."}

    try:
        with open(STATUS_FILE) as f:
            status = json.load(f)
        return status
    except Exception as e:
        return {"running": False, "error": f"Could not read status: {e}"}


async def run_server(host: str, port: int) -> None:
    """
    Run the gateway server with signal handling.

    Args:
        host: Host to bind to
        port: Port to listen on
    """
    server = GatewayServer(host=host, port=port)

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler():
        asyncio.create_task(server.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    await server.start()


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="WebSocket Gateway Server")
    parser.add_argument("--start", action="store_true", help="Start the gateway server")
    parser.add_argument("--status", action="store_true", help="Get server status")
    parser.add_argument("--health", action="store_true", help="Get health check")
    parser.add_argument("--host", default=None, help=f"Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument(
        "--port", type=int, default=None, help=f"Port to listen on (default: {DEFAULT_PORT})"
    )

    args = parser.parse_args()

    if args.start:
        config = load_config()
        host = args.host or config.get("host", DEFAULT_HOST)
        port = args.port or config.get("port", DEFAULT_PORT)

        print(f"Starting gateway on ws://{host}:{port}")
        asyncio.run(run_server(host, port))

    elif args.status:
        status = get_server_status()
        print("OK" if status.get("running") else "STOPPED")
        print(json.dumps(status, indent=2))

    elif args.health:
        # For health check, we need to connect to the running server
        status = get_server_status()
        if not status.get("running"):
            print("ERROR: Server not running")
            print(json.dumps(status, indent=2))
            sys.exit(1)

        # Try to connect and get health
        try:
            import websockets

            host = status.get("host", DEFAULT_HOST)
            port = status.get("port", DEFAULT_PORT)

            async def check_health():
                uri = f"ws://{host}:{port}"
                async with websockets.connect(uri) as ws:
                    await ws.send(json.dumps({"type": "status"}))
                    response = await ws.recv()
                    return json.loads(response)

            result = asyncio.run(check_health())
            print("OK")
            print(json.dumps(result.get("status", result), indent=2))

        except ImportError:
            print("ERROR: websockets library required for health check")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Could not connect to server: {e}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
