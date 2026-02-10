"""
Tool: Gateway Router
Purpose: Central message routing hub with integrated security pipeline

Routes messages between channel adapters and the agent. Implements the
security pipeline: sanitization -> user resolution -> rate limiting -> permissions.

Usage:
    python tools/channels/router.py --action status
    python tools/channels/router.py --action list-adapters
    python tools/channels/router.py --action test-security --user-id alice --content "test message"

Dependencies:
    - tools.security.sanitizer
    - tools.security.ratelimit
    - tools.security.permissions
    - tools.security.audit
    - tools.channels.inbox
    - tools.channels.models
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import ChannelUser, UnifiedMessage


def _log_to_dashboard(
    event_type: str,
    summary: str,
    channel: str = None,
    user_id: str = None,
    details: dict = None,
    severity: str = "info",
) -> None:
    """
    Log event to dashboard database.

    Fails silently to prevent logging from breaking message flow.
    """
    try:
        from tools.dashboard.backend.database import log_event

        log_event(event_type, summary, channel, user_id, details, severity)
    except Exception:
        pass  # Never let logging break message flow


def _record_dashboard_metric(
    metric_name: str,
    metric_value: float,
    labels: dict = None,
) -> None:
    """
    Record metric to dashboard database.

    Fails silently to prevent metrics from breaking message flow.
    """
    try:
        from tools.dashboard.backend.database import record_metric

        record_metric(metric_name, metric_value, labels)
    except Exception:
        pass


def _update_dex_state(
    state: str,
    current_task: str = None,
    broadcast: bool = True,
) -> None:
    """
    Update Dex avatar state in database and optionally broadcast to WebSocket clients.

    Valid states: idle, listening, thinking, working, success, error, sleeping, hyperfocus, waiting

    Fails silently to prevent state updates from breaking message flow.
    """
    try:
        from tools.dashboard.backend.database import set_dex_state

        set_dex_state(state, current_task)

        if broadcast:
            try:
                from tools.dashboard.backend.websocket import sync_broadcast_state_change

                sync_broadcast_state_change(state, current_task)
            except Exception:
                pass  # WebSocket broadcast failed, state still saved
    except Exception:
        pass  # Never let state updates break message flow


class ChannelAdapter(ABC):
    """
    Abstract base class for channel adapters.

    Each channel (Telegram, Discord, Slack) implements this interface
    to connect to the gateway and handle platform-specific messaging.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Channel name identifier.

        Returns:
            str: Channel name (e.g., 'telegram', 'discord', 'slack')
        """
        ...

    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to the channel.

        Should establish connection to the platform and start
        receiving messages.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Disconnect from the channel.

        Should cleanly close connection and stop receiving messages.
        """
        ...

    @abstractmethod
    async def send_message(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Send a message through this channel.

        Args:
            message: UnifiedMessage to send

        Returns:
            Dict with success status and message ID
        """
        ...

    @abstractmethod
    def to_unified(self, raw_message: Any) -> UnifiedMessage:
        """
        Convert platform-specific message to unified format.

        Args:
            raw_message: Platform-specific message object

        Returns:
            UnifiedMessage normalized from the platform message
        """
        ...

    @abstractmethod
    def from_unified(self, message: UnifiedMessage) -> Any:
        """
        Convert unified message to platform-specific format.

        Args:
            message: UnifiedMessage to convert

        Returns:
            Platform-specific message object
        """
        ...

    def set_router(self, router: "MessageRouter") -> None:
        """
        Set reference to the parent router.

        Args:
            router: The MessageRouter instance
        """
        self.router = router


class MessageRouter:
    """
    Routes messages between channels and agent with security checks.

    The router is the central hub that:
    1. Receives messages from channel adapters
    2. Runs the security pipeline (sanitize, rate limit, permissions)
    3. Dispatches to message handlers
    4. Routes outbound messages to appropriate channels
    """

    def __init__(self):
        self.adapters: dict[str, ChannelAdapter] = {}
        self.message_handlers: list[Callable] = []
        self.response_queue: asyncio.Queue = asyncio.Queue()
        self._started = False
        self._start_time: datetime | None = None

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        """
        Register a channel adapter.

        Args:
            adapter: ChannelAdapter instance to register
        """
        self.adapters[adapter.name] = adapter
        adapter.set_router(self)

    def unregister_adapter(self, name: str) -> None:
        """
        Unregister a channel adapter.

        Args:
            name: Name of the adapter to unregister
        """
        if name in self.adapters:
            del self.adapters[name]

    def get_adapter(self, name: str) -> ChannelAdapter | None:
        """
        Get a registered channel adapter by name.

        Args:
            name: Name of the adapter (e.g., 'telegram', 'discord')

        Returns:
            ChannelAdapter instance or None if not found
        """
        return self.adapters.get(name)

    def add_message_handler(self, handler: Callable) -> None:
        """
        Add handler for incoming messages.

        Handlers are called with (message, context) after security checks pass.

        Args:
            handler: Async callable that processes messages
        """
        self.message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable) -> None:
        """
        Remove a message handler.

        Args:
            handler: Handler to remove
        """
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)

    async def security_pipeline(self, message: UnifiedMessage) -> tuple[bool, str, dict[str, Any]]:
        """
        Run security checks on inbound message.

        Pipeline stages:
        1. Input sanitization - clean content, detect injection
        2. User resolution - look up or create user record
        3. Pairing check - verify user has completed pairing
        4. Rate limit check - enforce request throttling
        5. Permission check - verify user can send messages

        Args:
            message: UnifiedMessage to check

        Returns:
            Tuple of (allowed: bool, reason: str, context: dict)
        """
        context: dict[str, Any] = {}

        # 1. Input sanitization
        try:
            from tools.security import sanitizer

            sanitize_result = sanitizer.sanitize(message.content)
            context["sanitized"] = sanitize_result

            # Check if content should be blocked
            security = sanitize_result.get("security", {})
            recommendation = security.get("recommendation", "allow")
            if recommendation in ["block", "escalate"]:
                return False, "content_blocked", context

            # Use sanitized content
            message.content = sanitize_result.get("sanitized", message.content)

        except ImportError:
            # Sanitizer not available, skip
            context["sanitized"] = {"skipped": True}
        except Exception as e:
            context["sanitized"] = {"error": str(e)}

        # 2. Get user from channel
        try:
            from tools.channels import inbox

            user = inbox.get_user_by_channel(message.channel, message.channel_user_id)

            if not user:
                # New user - create but mark as unpaired
                user = ChannelUser(
                    id=str(uuid.uuid4()),
                    channel=message.channel,
                    channel_user_id=message.channel_user_id,
                    display_name=message.metadata.get("display_name", "Unknown"),
                    username=message.metadata.get("username"),
                    is_paired=False,
                )
                inbox.create_or_update_user(user)

            context["user"] = user.to_dict() if hasattr(user, "to_dict") else user
            message.user_id = user.id

        except Exception as e:
            context["user"] = {"error": str(e)}
            # Generate a temporary user ID if we can't look up
            if not message.user_id:
                message.user_id = f"temp_{message.channel}_{message.channel_user_id}"

        # 3. Check if user is paired (required for full access)
        user_obj = context.get("user", {})
        is_paired = (
            user_obj.get("is_paired", False)
            if isinstance(user_obj, dict)
            else getattr(user_obj, "is_paired", False)
        )

        if not is_paired:
            return False, "user_not_paired", context

        # 4. Rate limit check
        try:
            from tools.security import ratelimit

            rate_result = ratelimit.check_rate_limit(
                entity_type="user", entity_id=message.user_id, tokens=1, cost=0.0
            )
            context["rate_limit"] = rate_result

            if not rate_result.get("allowed", True):
                return False, "rate_limited", context

        except ImportError:
            context["rate_limit"] = {"skipped": True}
        except Exception as e:
            context["rate_limit"] = {"error": str(e)}

        # 5. Permission check
        try:
            from tools.security import permissions

            perm_result = permissions.check_permission(
                user_id=message.user_id, permission="chat:send"
            )
            context["permissions"] = perm_result

            if not perm_result.get("allowed", True):
                return False, "permission_denied", context

        except ImportError:
            context["permissions"] = {"skipped": True}
        except Exception as e:
            context["permissions"] = {"error": str(e)}

        return True, "ok", context

    async def route_inbound(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Process inbound message through security pipeline and dispatch to handlers.

        Args:
            message: UnifiedMessage from a channel adapter

        Returns:
            Dict with success status and processing results
        """
        start_time = time.time()

        # Update state to thinking while processing
        _update_dex_state("thinking", f"Processing message from {message.channel}")

        # Run security checks
        allowed, reason, context = await self.security_pipeline(message)

        # Log to audit
        try:
            from tools.security import audit

            audit.log_event(
                event_type="command",
                action="message_inbound",
                user_id=message.user_id,
                channel=message.channel,
                status="success" if allowed else "blocked",
                details={
                    "reason": reason,
                    "message_id": message.id,
                    "content_type": message.content_type,
                },
            )
        except ImportError:
            pass
        except Exception:
            pass

        if not allowed:
            # Log blocked message to dashboard
            _log_to_dashboard(
                event_type="message",
                summary=f"Blocked inbound message: {reason}",
                channel=message.channel,
                user_id=message.user_id,
                details={"reason": reason, "message_id": message.id},
                severity="warning",
            )
            # Return to idle state after blocking
            _update_dex_state("idle", None)

            # Record response time for blocked messages
            elapsed_ms = (time.time() - start_time) * 1000
            _record_dashboard_metric(
                metric_name="response_time_ms",
                metric_value=elapsed_ms,
                labels={"channel": message.channel, "success": "false", "reason": reason},
            )

            return {"success": False, "reason": reason, "context": context}

        # Log successful inbound message to dashboard
        _log_to_dashboard(
            event_type="message",
            summary=f"Received message from {message.channel}",
            channel=message.channel,
            user_id=message.user_id,
            details={
                "message_id": message.id,
                "content_type": message.content_type,
                "content_preview": message.content[:100] if message.content else None,
            },
            severity="info",
        )

        # Record inbound message metric
        _record_dashboard_metric(
            metric_name="messages_inbound",
            metric_value=1,
            labels={"channel": message.channel},
        )

        # Store message
        try:
            from tools.channels import inbox

            inbox.store_message(message)
        except Exception as e:
            context["storage_error"] = str(e)

        # Update state to working while executing handlers
        _update_dex_state("working", f"Handling message from {message.channel}")

        # Dispatch to handlers
        handler_results = []
        for handler in self.message_handlers:
            try:
                result = await handler(message, context)
                handler_results.append(
                    {"handler": handler.__name__, "success": True, "result": result}
                )
            except Exception as e:
                handler_results.append(
                    {"handler": handler.__name__, "success": False, "error": str(e)}
                )
                # Log handler error
                try:
                    from tools.security import audit

                    audit.log_event(
                        event_type="error",
                        action="handler_error",
                        user_id=message.user_id,
                        details={
                            "error": str(e),
                            "handler": handler.__name__,
                            "message_id": message.id,
                        },
                    )
                except Exception:
                    pass

        # Return to idle state after processing
        _update_dex_state("idle", None)

        # Record response time metric
        elapsed_ms = (time.time() - start_time) * 1000
        _record_dashboard_metric(
            metric_name="response_time_ms",
            metric_value=elapsed_ms,
            labels={"channel": message.channel, "success": "true"},
        )

        return {"success": True, "message_id": message.id, "handlers": handler_results}

    async def route_outbound(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Send message to appropriate channel.

        Args:
            message: UnifiedMessage to send

        Returns:
            Dict with success status and send results
        """
        channel = message.channel

        # If no channel specified, use user's preferred channel
        if not channel and message.user_id:
            try:
                from tools.channels import inbox

                channel = inbox.get_preferred_channel(message.user_id)
            except Exception:
                pass

        if not channel:
            return {"success": False, "error": "no_channel_specified"}

        adapter = self.adapters.get(channel)
        if not adapter:
            return {"success": False, "error": f"adapter_not_found:{channel}"}

        try:
            # Ensure message has an ID
            if not message.id:
                message.id = str(uuid.uuid4())

            # Update state while sending
            _update_dex_state("working", f"Sending response to {channel}")

            result = await adapter.send_message(message)

            # Store outbound message
            message.direction = "outbound"
            try:
                from tools.channels import inbox

                inbox.store_message(message)
            except Exception:
                pass

            # Log to audit
            try:
                from tools.security import audit

                audit.log_event(
                    event_type="command",
                    action="message_outbound",
                    user_id=message.user_id,
                    channel=channel,
                    status="success" if result.get("success") else "failure",
                    details={"message_id": message.id, "result": result},
                )
            except Exception:
                pass

            # Log to dashboard
            _log_to_dashboard(
                event_type="message",
                summary=f"Sent message to {channel}",
                channel=channel,
                user_id=message.user_id,
                details={
                    "message_id": message.id,
                    "content_preview": message.content[:100] if message.content else None,
                    "success": result.get("success"),
                },
                severity="info" if result.get("success") else "warning",
            )

            # Record outbound message metric
            _record_dashboard_metric(
                metric_name="messages_outbound",
                metric_value=1,
                labels={"channel": channel, "success": str(result.get("success", False))},
            )

            # Return to idle after sending
            _update_dex_state("idle", None)

            return result

        except Exception as e:
            # Log error
            try:
                from tools.security import audit

                audit.log_event(
                    event_type="error",
                    action="send_failed",
                    channel=channel,
                    details={"error": str(e), "message_id": message.id},
                )
            except Exception:
                pass
            # Set error state briefly, then idle
            _update_dex_state("error", f"Failed to send to {channel}")
            _update_dex_state("idle", None)
            return {"success": False, "error": str(e)}

    async def broadcast(
        self, user_id: str, content: str, priority: str = "normal"
    ) -> dict[str, Any]:
        """
        Send notification to user via their preferred channel.

        Args:
            user_id: Internal user ID
            content: Message content to send
            priority: Message priority ('low', 'normal', 'high')

        Returns:
            Dict with success status and send results
        """
        channel = None

        try:
            from tools.channels import inbox

            # Get preferred channel
            channel = inbox.get_preferred_channel(user_id)

            if not channel:
                # Get any linked channel
                links = inbox.get_linked_channels(user_id)
                if links:
                    channel = links[0]["channel"]

        except Exception:
            pass

        if not channel:
            return {"success": False, "error": "no_channel_for_user"}

        # Look up channel_user_id for the target channel
        channel_user_id = ""
        try:
            from tools.channels import inbox

            links = inbox.get_linked_channels(user_id)
            for link in links:
                if link["channel"] == channel:
                    channel_user_id = link["channel_user_id"]
                    break
        except Exception:
            pass

        message = UnifiedMessage(
            id=str(uuid.uuid4()),
            channel=channel,
            channel_message_id="",
            user_id=user_id,
            channel_user_id=channel_user_id,
            direction="outbound",
            content=content,
            metadata={"priority": priority},
        )

        return await self.route_outbound(message)

    def get_status(self) -> dict[str, Any]:
        """
        Get router status and statistics (synchronous).

        Returns:
            Dict with adapter status and metrics
        """
        return {
            "started": self._started,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "adapters": {name: {"connected": True} for name in self.adapters.keys()},
            "handler_count": len(self.message_handlers),
        }

    async def get_status_async(self) -> dict[str, Any]:
        """
        Get router status with live adapter health checks.

        Returns:
            Dict with adapter status including health check results
        """
        adapter_status = {}

        for name, adapter in self.adapters.items():
            if hasattr(adapter, "health_check"):
                try:
                    # Call health check with timeout
                    health = await asyncio.wait_for(
                        adapter.health_check(),
                        timeout=3.0
                    )
                    adapter_status[name] = health
                except asyncio.TimeoutError:
                    adapter_status[name] = {"connected": False, "error": "Health check timed out"}
                except Exception as e:
                    adapter_status[name] = {"connected": False, "error": str(e)[:100]}
            else:
                # Fallback for adapters without health_check
                adapter_status[name] = {"connected": True, "health_check": "not_implemented"}

        return {
            "started": self._started,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "adapters": adapter_status,
            "handler_count": len(self.message_handlers),
        }

    async def start(self) -> None:
        """Start the router and connect all adapters."""
        self._started = True
        self._start_time = datetime.now()

        for name, adapter in self.adapters.items():
            try:
                await adapter.connect()
            except Exception as e:
                try:
                    from tools.security import audit

                    audit.log_event(
                        event_type="error",
                        action="adapter_connect_failed",
                        channel=name,
                        details={"error": str(e)},
                    )
                except Exception:
                    pass

    async def stop(self) -> None:
        """Stop the router and disconnect all adapters."""
        for name, adapter in self.adapters.items():
            try:
                await adapter.disconnect()
            except Exception:
                pass

        self._started = False


# =============================================================================
# Singleton router instance
# =============================================================================

_router_instance: MessageRouter | None = None


def get_router() -> MessageRouter:
    """Get or create the singleton router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = MessageRouter()
    return _router_instance


# =============================================================================
# CLI Interface
# =============================================================================


def test_security_pipeline(user_id: str, content: str) -> dict[str, Any]:
    """
    Test the security pipeline with a mock message.

    Args:
        user_id: User ID to test with
        content: Message content to test

    Returns:
        Dict with pipeline results
    """
    router = get_router()

    message = UnifiedMessage(
        id=str(uuid.uuid4()),
        channel="cli",
        channel_message_id="test",
        channel_user_id=user_id,
        direction="inbound",
        content=content,
    )

    # Run security pipeline synchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        allowed, reason, context = loop.run_until_complete(router.security_pipeline(message))
        return {"allowed": allowed, "reason": reason, "context": context}
    finally:
        loop.close()


def main():
    parser = argparse.ArgumentParser(description="Gateway Router")
    parser.add_argument(
        "--action", required=True, choices=["status", "list-adapters", "test-security"]
    )
    parser.add_argument("--user-id", help="User ID for testing")
    parser.add_argument("--content", help="Content for testing")

    args = parser.parse_args()

    try:
        if args.action == "status":
            router = get_router()
            result = router.get_status()

        elif args.action == "list-adapters":
            router = get_router()
            result = {"adapters": list(router.adapters.keys()), "count": len(router.adapters)}

        elif args.action == "test-security":
            if not args.user_id or not args.content:
                print("ERROR: --user-id and --content required for test-security")
                sys.exit(1)
            result = test_security_pipeline(args.user_id, args.content)

        else:
            print(f"ERROR: Unknown action: {args.action}")
            sys.exit(1)

        print("OK")
        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
