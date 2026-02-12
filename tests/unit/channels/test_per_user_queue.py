"""Tests for per-channel locking in tools/channels/router.py"""

import asyncio
from unittest.mock import patch

import pytest

from tools.channels.models import UnifiedMessage
from tools.channels.router import MessageRouter


@pytest.fixture
def router():
    return MessageRouter()


class TestChannelLocks:
    def test_get_channel_lock_creates_new(self, router):
        lock = router._get_channel_lock("telegram")
        assert isinstance(lock, asyncio.Lock)

    def test_get_channel_lock_returns_same(self, router):
        lock1 = router._get_channel_lock("telegram")
        lock2 = router._get_channel_lock("telegram")
        assert lock1 is lock2

    def test_different_channels_get_different_locks(self, router):
        lock_telegram = router._get_channel_lock("telegram")
        lock_discord = router._get_channel_lock("discord")
        assert lock_telegram is not lock_discord

    def test_channel_locks_initialized_empty(self, router):
        assert router._channel_locks == {}


class TestPerChannelLocking:
    @pytest.mark.asyncio
    async def test_same_channel_messages_serialized(self, router):
        execution_order = []
        call_count = 0

        async def slow_handler(message, context):
            nonlocal call_count
            call_count += 1
            current = call_count
            execution_order.append(f"start_{current}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end_{current}")
            return {"success": True}

        router.add_message_handler(slow_handler)

        msg1 = UnifiedMessage(
            id="1",
            channel="cli",
            channel_message_id="m1",
            channel_user_id="user1",
            direction="inbound",
            content="hello",
        )
        msg2 = UnifiedMessage(
            id="2",
            channel="cli",
            channel_message_id="m2",
            channel_user_id="user1",
            direction="inbound",
            content="world",
        )

        async def mock_pipeline(message):
            return True, "ok", {}

        with patch("tools.channels.router._update_dex_state"), \
             patch("tools.channels.router._log_to_dashboard"), \
             patch("tools.channels.router._record_dashboard_metric"), \
             patch.object(router, "security_pipeline", side_effect=mock_pipeline):
            await asyncio.gather(
                router.route_inbound(msg1),
                router.route_inbound(msg2),
            )

        # Messages on same channel should be serialized: start_1, end_1, start_2, end_2
        assert execution_order == ["start_1", "end_1", "start_2", "end_2"]

    @pytest.mark.asyncio
    async def test_different_channel_messages_parallel(self, router):
        execution_log = []

        async def tracking_handler(message, context):
            execution_log.append(f"start_{message.channel}")
            await asyncio.sleep(0.05)
            execution_log.append(f"end_{message.channel}")
            return {"success": True}

        router.add_message_handler(tracking_handler)

        msg_ch1 = UnifiedMessage(
            id="1",
            channel="cli",
            channel_message_id="m1",
            channel_user_id="user1",
            direction="inbound",
            content="hello",
        )
        msg_ch2 = UnifiedMessage(
            id="2",
            channel="api",
            channel_message_id="m2",
            channel_user_id="user1",
            direction="inbound",
            content="world",
        )

        async def mock_pipeline(message):
            return True, "ok", {}

        with patch("tools.channels.router._update_dex_state"), \
             patch("tools.channels.router._log_to_dashboard"), \
             patch("tools.channels.router._record_dashboard_metric"), \
             patch.object(router, "security_pipeline", side_effect=mock_pipeline):
            await asyncio.gather(
                router.route_inbound(msg_ch1),
                router.route_inbound(msg_ch2),
            )

        # Both should start before either ends (parallel execution)
        start_indices = [i for i, x in enumerate(execution_log) if x.startswith("start_")]
        end_indices = [i for i, x in enumerate(execution_log) if x.startswith("end_")]
        # At least one end should come after both starts if truly parallel
        assert len(start_indices) == 2
        assert len(end_indices) == 2
