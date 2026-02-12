"""Tests for tools/agent/config_models.py"""

from unittest.mock import patch

import pytest

from tools.agent.config_models import (
    AgentConfig,
    MemoryConfig,
    MultimodalConfig,
    RoutingConfig,
    SecurityConfig,
    WorkspaceConfig,
    load_and_validate,
)


class TestAgentConfig:
    def test_defaults(self):
        config = AgentConfig()
        assert config.agent.model == "claude-sonnet-4-20250514"
        assert config.agent.max_tokens == 4096
        assert config.adhd.response.strip_preamble is True
        assert config.sandbox.enabled is True

    def test_valid_overrides(self):
        config = AgentConfig(
            agent={"model": "custom-model", "max_tokens": 8192},
            adhd={"response": {"max_length_chat": 300}},
        )
        assert config.agent.model == "custom-model"
        assert config.agent.max_tokens == 8192
        assert config.adhd.response.max_length_chat == 300

    def test_extra_keys_allowed(self):
        config = AgentConfig(
            agent={"model": "test", "unknown_field": "value"},
        )
        assert config.agent.model == "test"

    def test_invalid_max_tokens_uses_default(self):
        with pytest.raises(ValueError):
            AgentConfig(agent={"max_tokens": -1})


class TestRoutingConfig:
    def test_defaults(self):
        config = RoutingConfig()
        assert config.routing.profile == "anthropic_only"
        assert config.routing.enabled is True
        assert config.budget.max_per_session_usd == 5.0
        assert config.exacto.enabled is True

    def test_valid_budget(self):
        config = RoutingConfig(
            budget={"max_per_day_usd": 100.0, "limit_action": "block"},
        )
        assert config.budget.max_per_day_usd == 100.0
        assert config.budget.limit_action == "block"


class TestMemoryConfig:
    def test_defaults(self):
        config = MemoryConfig()
        assert config.embeddings.model == "text-embedding-3-small"
        assert config.embeddings.dimensions == 1536
        assert config.search.default_type == "hybrid"
        assert config.extraction.gate_threshold == 0.3

    def test_valid_overrides(self):
        config = MemoryConfig(
            embeddings={"model": "custom-embedding", "dimensions": 768},
        )
        assert config.embeddings.model == "custom-embedding"
        assert config.embeddings.dimensions == 768


class TestMultimodalConfig:
    def test_defaults(self):
        config = MultimodalConfig()
        assert config.processing.enabled is True
        assert config.processing.vision.max_images_per_message == 3
        assert config.generation.model == "dall-e-3"

    def test_valid_overrides(self):
        config = MultimodalConfig(
            processing={"max_file_size_mb": 100},
        )
        assert config.processing.max_file_size_mb == 100


class TestSecurityConfig:
    def test_defaults(self):
        config = SecurityConfig()
        assert config.session.token_bytes == 32
        assert config.auth.max_failed_attempts == 5
        assert config.audit.enabled is True

    def test_valid_overrides(self):
        config = SecurityConfig(
            session={"token_bytes": 64, "max_concurrent": 10},
        )
        assert config.session.token_bytes == 64
        assert config.session.max_concurrent == 10


class TestWorkspaceConfig:
    def test_defaults(self):
        config = WorkspaceConfig()
        assert config.workspace.enabled is True
        assert config.workspace.base_path == "data/workspaces"
        assert config.workspace.access.default == "rw"

    def test_valid_overrides(self):
        config = WorkspaceConfig(
            workspace={"enabled": False, "base_path": "/custom/path"},
        )
        assert config.workspace.enabled is False
        assert config.workspace.base_path == "/custom/path"


class TestLoadAndValidate:
    def test_unknown_config_raises(self):
        with pytest.raises(ValueError, match="Unknown config"):
            load_and_validate("nonexistent_config")

    def test_missing_file_returns_defaults(self, tmp_path):
        with patch("tools.agent.config_models.ARGS_DIR", tmp_path):
            config = load_and_validate("agent")
            assert isinstance(config, AgentConfig)
            assert config.agent.model == "claude-sonnet-4-20250514"

    def test_explicit_model_class(self, tmp_path):
        with patch("tools.agent.config_models.ARGS_DIR", tmp_path):
            config = load_and_validate("custom", AgentConfig)
            assert isinstance(config, AgentConfig)

    def test_valid_yaml_loads(self, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("agent:\n  model: 'test-model'\n  max_tokens: 2048\n")
        with patch("tools.agent.config_models.ARGS_DIR", tmp_path):
            config = load_and_validate("agent")
            assert config.agent.model == "test-model"
            assert config.agent.max_tokens == 2048

    def test_invalid_yaml_returns_defaults(self, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("agent:\n  max_tokens: -999\n")
        with patch("tools.agent.config_models.ARGS_DIR", tmp_path):
            config = load_and_validate("agent")
            assert isinstance(config, AgentConfig)

    def test_empty_yaml_returns_defaults(self, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("")
        with patch("tools.agent.config_models.ARGS_DIR", tmp_path):
            config = load_and_validate("agent")
            assert isinstance(config, AgentConfig)
            assert config.agent.model == "claude-sonnet-4-20250514"
