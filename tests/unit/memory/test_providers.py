"""
Unit tests for memory provider implementations.

Tests the pluggable memory provider architecture including:
- Base class data structures
- NativeProvider operations
- ClaudeMemProvider operations
- Provider factory function
"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import os


# ============================================================================
# Data Structure Tests
# ============================================================================


class TestMemoryEntry:
    """Tests for MemoryEntry data class."""

    def test_create_basic_entry(self):
        """Test creating a basic memory entry."""
        from tools.memory.providers.base import MemoryEntry, MemoryType, MemorySource

        entry = MemoryEntry(
            id="test-1",
            content="User prefers dark mode",
            type=MemoryType.PREFERENCE,
        )

        assert entry.id == "test-1"
        assert entry.content == "User prefers dark mode"
        assert entry.type == MemoryType.PREFERENCE
        assert entry.source == MemorySource.USER
        assert entry.importance == 5

    def test_entry_to_dict(self):
        """Test converting entry to dictionary."""
        from tools.memory.providers.base import MemoryEntry, MemoryType, MemorySource

        entry = MemoryEntry(
            id="test-2",
            content="Test content",
            type=MemoryType.FACT,
            importance=8,
            tags=["test", "example"],
        )

        d = entry.to_dict()

        assert d["id"] == "test-2"
        assert d["content"] == "Test content"
        assert d["type"] == "fact"
        assert d["importance"] == 8
        assert d["tags"] == ["test", "example"]

    def test_entry_from_dict(self):
        """Test creating entry from dictionary."""
        from tools.memory.providers.base import MemoryEntry, MemoryType

        data = {
            "id": "test-3",
            "content": "From dict",
            "type": "preference",
            "importance": 7,
        }

        entry = MemoryEntry.from_dict(data)

        assert entry.id == "test-3"
        assert entry.content == "From dict"
        assert entry.type == MemoryType.PREFERENCE
        assert entry.importance == 7


class TestSearchFilters:
    """Tests for SearchFilters data class."""

    def test_empty_filters(self):
        """Test creating empty filters."""
        from tools.memory.providers.base import SearchFilters

        filters = SearchFilters()

        assert filters.types is None
        assert filters.min_importance is None
        assert filters.user_id is None

    def test_filters_to_dict(self):
        """Test converting filters to dictionary."""
        from tools.memory.providers.base import SearchFilters, MemoryType

        filters = SearchFilters(
            types=[MemoryType.FACT, MemoryType.PREFERENCE],
            min_importance=5,
            user_id="test-user",
        )

        d = filters.to_dict()

        assert d["types"] == ["fact", "preference"]
        assert d["min_importance"] == 5
        assert d["user_id"] == "test-user"


class TestDeploymentMode:
    """Tests for DeploymentMode enum."""

    def test_deployment_modes(self):
        """Test all deployment modes exist."""
        from tools.memory.providers.base import DeploymentMode

        assert DeploymentMode.CLOUD == "cloud"
        assert DeploymentMode.SELF_HOSTED == "self_hosted"
        assert DeploymentMode.LOCAL == "local"


# ============================================================================
# Provider Factory Tests
# ============================================================================


class TestProviderFactory:
    """Tests for the provider factory function."""

    def test_get_native_provider(self):
        """Test getting native provider."""
        from tools.memory.providers import get_provider, NativeProvider

        provider = get_provider("native")
        assert isinstance(provider, NativeProvider)
        assert provider.name == "native"

    def test_get_unknown_provider_raises(self):
        """Test that unknown provider raises ValueError."""
        from tools.memory.providers import get_provider

        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    def test_provider_with_config(self):
        """Test provider accepts configuration."""
        from tools.memory.providers import get_provider

        config = {"database_path": "data/test.db"}
        provider = get_provider("native", config)

        assert provider.name == "native"


# ============================================================================
# NativeProvider Tests
# ============================================================================


class TestNativeProvider:
    """Tests for NativeProvider."""

    def test_provider_properties(self):
        """Test native provider properties."""
        from tools.memory.providers.native import NativeProvider
        from tools.memory.providers.base import DeploymentMode

        provider = NativeProvider()

        assert provider.name == "native"
        assert provider.deployment_mode == DeploymentMode.LOCAL
        assert provider.supports_local is True
        assert provider.supports_cloud is False
        assert provider.supports_self_hosted is False

    @pytest.mark.asyncio
    async def test_check_dependencies(self):
        """Test dependency check (always ready for native)."""
        from tools.memory.providers.native import NativeProvider

        provider = NativeProvider()
        status = await provider.check_dependencies()

        assert status.ready is True
        assert "sqlite" in status.dependencies
        assert status.dependencies["sqlite"] is True

    @pytest.mark.asyncio
    async def test_bootstrap(self):
        """Test bootstrapping native provider."""
        from tools.memory.providers.native import NativeProvider

        provider = NativeProvider()
        result = await provider.bootstrap()

        assert result.success is True
        assert "table:memory_entries" in result.created

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check."""
        from tools.memory.providers.native import NativeProvider

        provider = NativeProvider()
        await provider.bootstrap()

        health = await provider.health_check()

        assert health.provider == "native"
        assert health.latency_ms >= 0


# ============================================================================
# ClaudeMemProvider Tests
# ============================================================================


class TestClaudeMemProvider:
    """Tests for ClaudeMemProvider."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield str(db_path)

    def test_provider_properties(self):
        """Test ClaudeMem provider properties."""
        from tools.memory.providers.claudemem_provider import ClaudeMemProvider
        from tools.memory.providers.base import DeploymentMode

        provider = ClaudeMemProvider()

        assert provider.name == "claudemem"
        assert provider.deployment_mode == DeploymentMode.LOCAL
        assert provider.supports_local is True
        assert provider.supports_cloud is False

    @pytest.mark.asyncio
    async def test_check_dependencies(self, temp_db):
        """Test dependency check."""
        from tools.memory.providers.claudemem_provider import ClaudeMemProvider

        provider = ClaudeMemProvider({"database_path": temp_db})
        status = await provider.check_dependencies()

        assert status.ready is True
        assert "sqlite" in status.dependencies

    @pytest.mark.asyncio
    async def test_add_and_get(self, temp_db):
        """Test adding and retrieving a memory."""
        from tools.memory.providers.claudemem_provider import ClaudeMemProvider
        from tools.memory.providers.base import MemoryType

        provider = ClaudeMemProvider({"database_path": temp_db})
        await provider.bootstrap()

        # Add memory
        entry_id = await provider.add(
            content="Test memory content",
            type=MemoryType.FACT,
            importance=7,
        )

        assert entry_id is not None

        # Get memory
        entry = await provider.get(entry_id)

        assert entry is not None
        assert entry.content == "Test memory content"
        assert entry.type == MemoryType.FACT
        assert entry.importance == 7

    @pytest.mark.asyncio
    async def test_search(self, temp_db):
        """Test searching memories."""
        from tools.memory.providers.claudemem_provider import ClaudeMemProvider
        from tools.memory.providers.base import MemoryType

        provider = ClaudeMemProvider({
            "database_path": temp_db,
            "embedding_model": "none",  # Skip embeddings for test
        })
        await provider.bootstrap()

        # Add test memories
        await provider.add(content="User prefers dark mode", type=MemoryType.PREFERENCE)
        await provider.add(content="User likes Python", type=MemoryType.FACT)
        await provider.add(content="User uses VSCode", type=MemoryType.FACT)

        # Search
        results = await provider.search("dark mode", limit=5)

        assert len(results) > 0
        # First result should match "dark mode"
        assert "dark" in results[0].content.lower() or "mode" in results[0].content.lower()

    @pytest.mark.asyncio
    async def test_update_and_delete(self, temp_db):
        """Test updating and deleting a memory."""
        from tools.memory.providers.claudemem_provider import ClaudeMemProvider
        from tools.memory.providers.base import MemoryType

        provider = ClaudeMemProvider({"database_path": temp_db})
        await provider.bootstrap()

        # Add memory
        entry_id = await provider.add(content="Original content", type=MemoryType.FACT)

        # Update
        success = await provider.update(entry_id, content="Updated content")
        assert success is True

        entry = await provider.get(entry_id)
        assert entry.content == "Updated content"

        # Delete
        success = await provider.delete(entry_id)
        assert success is True

        # Verify deleted (soft delete)
        entry = await provider.get(entry_id)
        # Soft delete means entry might still exist but marked inactive
        # For ClaudeMem, get returns None for inactive entries
        assert entry is None

    @pytest.mark.asyncio
    async def test_commitments(self, temp_db):
        """Test commitment tracking."""
        from tools.memory.providers.claudemem_provider import ClaudeMemProvider
        from datetime import datetime, timedelta

        provider = ClaudeMemProvider({"database_path": temp_db})
        await provider.bootstrap()

        # Add commitment
        commitment_id = await provider.add_commitment(
            content="Send the report to Sarah",
            user_id="test-user",
            target_person="Sarah",
            due_date=datetime.now() + timedelta(days=1),
        )

        assert commitment_id is not None

        # List commitments
        commitments = await provider.list_commitments(user_id="test-user")

        assert len(commitments) == 1
        assert commitments[0]["content"] == "Send the report to Sarah"
        assert commitments[0]["target_person"] == "Sarah"

        # Complete commitment
        success = await provider.complete_commitment(commitment_id)
        assert success is True

        # List again (should be empty for active)
        active = await provider.list_commitments(user_id="test-user", status="active")
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_context_capture_and_resume(self, temp_db):
        """Test context capture and resume."""
        from tools.memory.providers.claudemem_provider import ClaudeMemProvider

        provider = ClaudeMemProvider({"database_path": temp_db})
        await provider.bootstrap()

        # Capture context
        snapshot_id = await provider.capture_context(
            user_id="test-user",
            state={
                "active_file": "src/main.py",
                "last_action": "Added logging",
                "next_step": "Write tests",
            },
            trigger="manual",
            summary="Working on main module",
        )

        assert snapshot_id is not None

        # Resume context
        context = await provider.resume_context(user_id="test-user")

        assert context is not None
        assert context["next_step"] == "Write tests"
        assert context["active_file"] == "src/main.py"

        # List contexts
        contexts = await provider.list_contexts(user_id="test-user")

        assert len(contexts) == 1
        assert contexts[0]["summary"] == "Working on main module"


# ============================================================================
# MemoryService Tests
# ============================================================================


class TestMemoryService:
    """Tests for MemoryService facade."""

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test service initializes with default provider."""
        from tools.memory.service import MemoryService

        service = MemoryService()
        success = await service.initialize()

        assert success is True
        assert service.provider is not None
        assert service.provider.name == "native"

    @pytest.mark.asyncio
    async def test_service_health_check(self):
        """Test service health check."""
        from tools.memory.service import MemoryService

        service = MemoryService()
        await service.initialize()

        health = await service.health_check()

        assert health.healthy is True
        assert health.provider == "native"

    @pytest.mark.asyncio
    async def test_service_add_and_search(self):
        """Test adding and searching through service."""
        from tools.memory.service import MemoryService
        from tools.memory.providers.base import MemoryType

        service = MemoryService()
        await service.initialize()

        # Add memory
        entry_id = await service.add(
            content="Test service memory",
            type=MemoryType.FACT,
        )

        assert entry_id is not None

        # Search
        results = await service.search("test service")

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_service_commitments(self):
        """Test commitment operations through service."""
        from tools.memory.service import MemoryService

        service = MemoryService()
        await service.initialize()

        # Add commitment
        commitment_id = await service.add_commitment(
            content="Call mom",
            user_id="test-user",
            target_person="Mom",
        )

        assert commitment_id is not None

        # List
        commitments = await service.list_commitments(user_id="test-user")
        assert len(commitments) > 0

    @pytest.mark.asyncio
    async def test_service_context(self):
        """Test context operations through service."""
        from tools.memory.service import MemoryService

        service = MemoryService()
        await service.initialize()

        # Capture
        snapshot_id = await service.capture_context(
            user_id="test-user",
            state={"next_step": "Test context"},
            trigger="test",
        )

        assert snapshot_id is not None

        # Resume
        context = await service.resume_context(user_id="test-user")
        assert context is not None
