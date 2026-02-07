"""
Tests for SystemPromptBuilder

Tests the system prompt generation from workspace files and runtime context.
"""

import tempfile
from pathlib import Path

import pytest

from tools.agent.system_prompt import (
    SystemPromptBuilder,
    PromptContext,
    PromptMode,
    SessionType,
    SESSION_FILE_ALLOWLISTS,
    bootstrap_workspace,
    is_workspace_bootstrapped,
    TEMPLATES_PATH,
    BOOTSTRAP_FILES,
    FALLBACK_IDENTITY,
)


class TestPromptMode:
    """Tests for PromptMode enum."""

    def test_prompt_mode_values(self):
        """Test prompt mode enum values."""
        assert PromptMode.FULL.value == "full"
        assert PromptMode.MINIMAL.value == "minimal"
        assert PromptMode.NONE.value == "none"

    def test_prompt_mode_from_string(self):
        """Test creating prompt mode from string."""
        assert PromptMode("full") == PromptMode.FULL
        assert PromptMode("minimal") == PromptMode.MINIMAL
        assert PromptMode("none") == PromptMode.NONE


class TestPromptContext:
    """Tests for PromptContext dataclass."""

    def test_default_values(self):
        """Test default context values."""
        ctx = PromptContext(user_id="test")
        assert ctx.user_id == "test"
        assert ctx.timezone == "UTC"
        assert ctx.current_time is None
        assert ctx.tools == []
        assert ctx.session_type == SessionType.MAIN
        assert ctx.prompt_mode == PromptMode.FULL  # Default for MAIN session
        assert ctx.channel == "direct"
        assert ctx.is_subagent is False
        assert ctx.workspace_root is None

    def test_prompt_mode_conversion(self):
        """Test string to enum conversion."""
        ctx = PromptContext(user_id="test", prompt_mode="minimal")
        assert ctx.prompt_mode == PromptMode.MINIMAL

    def test_session_type_conversion(self):
        """Test string to SessionType enum conversion."""
        ctx = PromptContext(user_id="test", session_type="subagent")
        assert ctx.session_type == SessionType.SUBAGENT

    def test_subagent_default_prompt_mode(self):
        """Test that subagent sessions default to MINIMAL mode."""
        ctx = PromptContext(user_id="test", session_type=SessionType.SUBAGENT)
        assert ctx.prompt_mode == PromptMode.MINIMAL

    def test_heartbeat_default_prompt_mode(self):
        """Test that heartbeat sessions default to MINIMAL mode."""
        ctx = PromptContext(user_id="test", session_type=SessionType.HEARTBEAT)
        assert ctx.prompt_mode == PromptMode.MINIMAL

    def test_file_allowlist_main(self):
        """Test that main sessions get all files."""
        ctx = PromptContext(user_id="test", session_type=SessionType.MAIN)
        assert "PERSONA.md" in ctx.file_allowlist
        assert "IDENTITY.md" in ctx.file_allowlist
        assert "USER.md" in ctx.file_allowlist
        assert "AGENTS.md" in ctx.file_allowlist

    def test_file_allowlist_subagent(self):
        """Test that subagent sessions only get PERSONA + AGENTS."""
        ctx = PromptContext(user_id="test", session_type=SessionType.SUBAGENT)
        assert "PERSONA.md" in ctx.file_allowlist
        assert "AGENTS.md" in ctx.file_allowlist
        assert "USER.md" not in ctx.file_allowlist
        assert "IDENTITY.md" not in ctx.file_allowlist

    def test_include_runtime_context_main(self):
        """Test that main sessions include runtime context."""
        ctx = PromptContext(user_id="test", session_type=SessionType.MAIN)
        assert ctx.include_runtime_context is True

    def test_include_runtime_context_subagent(self):
        """Test that subagent sessions don't include runtime context."""
        ctx = PromptContext(user_id="test", session_type=SessionType.SUBAGENT)
        assert ctx.include_runtime_context is False

    def test_workspace_path_conversion(self):
        """Test workspace path conversion to Path."""
        ctx = PromptContext(user_id="test", workspace_root="/tmp/test")
        assert isinstance(ctx.workspace_root, Path)
        assert ctx.workspace_root == Path("/tmp/test")


class TestBootstrap:
    """Tests for workspace bootstrap functions."""

    def test_bootstrap_workspace(self):
        """Test bootstrapping a new workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Bootstrap
            result = bootstrap_workspace(workspace)

            assert result["success"] is True
            assert len(result["created"]) > 0
            assert len(result["skipped"]) == 0

            # Verify files were created
            assert (workspace / "PERSONA.md").exists()
            assert (workspace / "IDENTITY.md").exists()
            assert (workspace / "USER.md").exists()

    def test_bootstrap_skips_existing(self):
        """Test that bootstrap skips existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create an existing file
            (workspace / "PERSONA.md").write_text("existing content")

            # Bootstrap
            result = bootstrap_workspace(workspace)

            assert "PERSONA.md" in result["skipped"]
            assert (workspace / "PERSONA.md").read_text() == "existing content"

    def test_bootstrap_force_overwrites(self):
        """Test that force=True overwrites existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create an existing file
            (workspace / "PERSONA.md").write_text("existing content")

            # Bootstrap with force
            result = bootstrap_workspace(workspace, force=True)

            assert "PERSONA.md" in result["created"]
            assert (workspace / "PERSONA.md").read_text() != "existing content"

    def test_is_workspace_bootstrapped(self):
        """Test workspace bootstrap detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Not bootstrapped initially
            assert is_workspace_bootstrapped(workspace) is False

            # Create PERSONA.md
            (workspace / "PERSONA.md").write_text("test")

            # Now bootstrapped
            assert is_workspace_bootstrapped(workspace) is True


class TestSystemPromptBuilder:
    """Tests for SystemPromptBuilder."""

    def test_prompt_mode_none(self):
        """Test NONE mode returns minimal identity."""
        builder = SystemPromptBuilder()
        ctx = PromptContext(user_id="test", prompt_mode=PromptMode.NONE)
        prompt = builder.build(ctx)

        assert "Dex" in prompt
        assert len(prompt) < 100
        assert prompt == FALLBACK_IDENTITY

    def test_prompt_mode_minimal(self):
        """Test MINIMAL mode includes core + safety only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                prompt_mode=PromptMode.MINIMAL,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should have core identity and safety
            assert "Safety" in prompt or "safety" in prompt.lower()
            # Should NOT have user context
            assert "About the User" not in prompt

    def test_prompt_mode_full(self):
        """Test FULL mode includes all sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                prompt_mode=PromptMode.FULL,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should have ADHD principles
            assert "ADHD" in prompt
            # Should have temporal context
            assert "Current Context" in prompt or "Timezone" in prompt

    def test_channel_rules_discord(self):
        """Test Discord channel rules are included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                channel="discord",
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            assert "discord" in prompt.lower()

    def test_channel_rules_telegram(self):
        """Test Telegram channel rules are included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                channel="telegram",
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            assert "telegram" in prompt.lower()

    def test_channel_rules_direct(self):
        """Test direct channel has no special rules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                channel="direct",
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should not have channel-specific rules
            assert "Channel Rules" not in prompt

    def test_fallback_without_workspace(self):
        """Test fallback when workspace files don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)  # Empty workspace

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                prompt_mode=PromptMode.FULL,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should still get fallback identity
            assert "Dex" in prompt

    def test_config_disables_sections(self):
        """Test that config can disable sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            config = {
                "sections": {
                    "soul": True,
                    "identity": False,  # Disabled
                    "user": False,  # Disabled
                    "agents": False,  # Disabled
                    "tools": False,  # Disabled
                    "safety": True,
                    "temporal": False,  # Disabled
                    "channel_rules": False,  # Disabled
                }
            }

            builder = SystemPromptBuilder(config)
            ctx = PromptContext(
                user_id="test",
                prompt_mode=PromptMode.FULL,
                workspace_root=workspace,
                channel="discord",
            )
            prompt = builder.build(ctx)

            # Should have soul and safety
            assert "ADHD" in prompt or "Dex" in prompt
            assert "Safety" in prompt or "safety" in prompt.lower()
            # Should NOT have disabled sections
            assert "About the User" not in prompt
            assert "Channel Rules" not in prompt

    def test_strips_frontmatter(self):
        """Test that YAML frontmatter is stripped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create file with frontmatter
            (workspace / "PERSONA.md").write_text("""---
summary: "Test"
---

# Test Content

This is the actual content.""")

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should not have frontmatter
            assert "summary:" not in prompt
            assert "---" not in prompt
            # Should have content
            assert "Test Content" in prompt


class TestTemplatesExist:
    """Tests that template files exist."""

    def test_templates_directory_exists(self):
        """Test templates directory exists."""
        assert TEMPLATES_PATH.exists()
        assert TEMPLATES_PATH.is_dir()

    def test_required_templates_exist(self):
        """Test all required template files exist."""
        for filename in BOOTSTRAP_FILES:
            template_path = TEMPLATES_PATH / filename
            assert template_path.exists(), f"Template {filename} not found"

    def test_persona_template_has_adhd_content(self):
        """Test PERSONA.md has ADHD-specific content."""
        persona = (TEMPLATES_PATH / "PERSONA.md").read_text()
        assert "ADHD" in persona
        assert "ONE THING AT A TIME" in persona or "one thing" in persona.lower()


class TestSessionBasedFiltering:
    """Tests for session-based file filtering (inspired by OpenClaw)."""

    def test_session_file_allowlists_defined(self):
        """Test that all session types have defined allowlists."""
        assert SessionType.MAIN in SESSION_FILE_ALLOWLISTS
        assert SessionType.SUBAGENT in SESSION_FILE_ALLOWLISTS
        assert SessionType.HEARTBEAT in SESSION_FILE_ALLOWLISTS
        assert SessionType.CRON in SESSION_FILE_ALLOWLISTS

    def test_subagent_only_gets_persona_and_agents(self):
        """Test that subagent sessions only get PERSONA.md and AGENTS.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                session_type=SessionType.SUBAGENT,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should have PERSONA content (ADHD principles)
            assert "ADHD" in prompt or "Dex" in prompt

            # Should have safety
            assert "Safety" in prompt or "safety" in prompt.lower()

            # Should NOT have user profile section
            assert "About the User" not in prompt

            # Should NOT have identity customizations header
            # (IDENTITY.md content is not in subagent allowlist)

    def test_heartbeat_gets_heartbeat_file(self):
        """Test that heartbeat sessions get HEARTBEAT.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                session_type=SessionType.HEARTBEAT,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should have heartbeat content
            assert "Heartbeat" in prompt or "heartbeat" in prompt.lower()

    def test_main_session_gets_all_files(self):
        """Test that main sessions get all workspace files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            # Add some content to USER.md to verify it's included
            (workspace / "USER.md").write_text("# About You\n\nTest user content here.")

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                session_type=SessionType.MAIN,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should have user content
            assert "About the User" in prompt or "Test user content" in prompt

    def test_subagent_shorter_than_main(self):
        """Test that subagent prompts are shorter than main prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()

            # Main session
            main_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.MAIN,
                workspace_root=workspace,
            )
            main_prompt = builder.build(main_ctx)

            # Subagent session
            sub_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.SUBAGENT,
                workspace_root=workspace,
            )
            sub_prompt = builder.build(sub_ctx)

            # Subagent should be significantly shorter
            assert len(sub_prompt) < len(main_prompt)

    def test_cron_minimal_context(self):
        """Test that cron sessions get minimal context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test",
                session_type=SessionType.CRON,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # Should have core identity
            assert "Dex" in prompt or "ADHD" in prompt

            # Should NOT have user profile
            assert "About the User" not in prompt

            # Should NOT have heartbeat (cron doesn't get HEARTBEAT.md)
            # Note: This checks the allowlist, not content presence

    def test_channel_rules_only_for_main_sessions(self):
        """Test that channel rules are only added for main sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()

            # Main session on discord - should have channel rules
            main_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.MAIN,
                channel="discord",
                workspace_root=workspace,
            )
            main_prompt = builder.build(main_ctx)
            assert "discord" in main_prompt.lower()

            # Subagent on discord - should NOT have channel rules
            sub_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.SUBAGENT,
                channel="discord",
                workspace_root=workspace,
            )
            sub_prompt = builder.build(sub_ctx)
            assert "Channel Rules" not in sub_prompt


class TestIntegration:
    """Integration tests for the full prompt building flow."""

    def test_full_bootstrap_and_build(self):
        """Test complete bootstrap and prompt build flow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # 1. Check not bootstrapped
            assert not is_workspace_bootstrapped(workspace)

            # 2. Bootstrap
            result = bootstrap_workspace(workspace)
            assert result["success"]

            # 3. Check bootstrapped
            assert is_workspace_bootstrapped(workspace)

            # 4. Build prompt
            builder = SystemPromptBuilder()
            ctx = PromptContext(
                user_id="test_user",
                timezone="America/Los_Angeles",
                channel="telegram",
                session_type=SessionType.MAIN,
                workspace_root=workspace,
            )
            prompt = builder.build(ctx)

            # 5. Verify prompt content
            assert len(prompt) > 100
            assert "Dex" in prompt
            assert "telegram" in prompt.lower()

    def test_subagent_gets_minimal_prompt(self):
        """Test that subagents get minimal prompts via session type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            builder = SystemPromptBuilder()

            # Main agent - full prompt
            main_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.MAIN,
                workspace_root=workspace,
            )
            main_prompt = builder.build(main_ctx)

            # Subagent - automatically gets minimal prompt
            sub_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.SUBAGENT,
                workspace_root=workspace,
            )
            sub_prompt = builder.build(sub_ctx)

            # Subagent prompt should be shorter
            assert len(sub_prompt) < len(main_prompt)

    def test_session_type_controls_file_access(self):
        """Test that session type controls which files are loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bootstrap_workspace(workspace)

            # Add unique content to each file for verification
            (workspace / "USER.md").write_text("# USER FILE MARKER")
            (workspace / "IDENTITY.md").write_text("# IDENTITY FILE MARKER")

            builder = SystemPromptBuilder()

            # Main session should have both markers
            main_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.MAIN,
                workspace_root=workspace,
            )
            main_prompt = builder.build(main_ctx)
            assert "USER FILE MARKER" in main_prompt
            assert "IDENTITY FILE MARKER" in main_prompt

            # Subagent should have neither
            sub_ctx = PromptContext(
                user_id="test",
                session_type=SessionType.SUBAGENT,
                workspace_root=workspace,
            )
            sub_prompt = builder.build(sub_ctx)
            assert "USER FILE MARKER" not in sub_prompt
            assert "IDENTITY FILE MARKER" not in sub_prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
