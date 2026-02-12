"""
Tests for install.sh — the DexAI Docker-first installer.

Runs install.sh via subprocess with stub executables on PATH so that
tests execute in a sandbox with no network, no real installs, and no
side effects outside tmp_path.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest


INSTALL_SCRIPT = Path(__file__).parent.parent.parent / "install.sh"


def run_install(
    *args: str,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    """Run install.sh and return CompletedProcess."""
    return subprocess.run(
        ["bash", str(INSTALL_SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


# Helper shared across test classes
def _env_without_stub(stubbed_env: dict, stub_name: str) -> dict[str, str]:
    """Return a copy of stubbed_env with one stub removed."""
    env = stubbed_env.copy()
    bin_dir = env["PATH"].split(":")[0]
    stub_path = Path(bin_dir) / stub_name
    if stub_path.exists():
        stub_path.unlink()
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Argument Parsing
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestArgumentParsing:
    """Tests for CLI argument parsing."""

    def test_help_flag_exits_zero(self):
        result = run_install("--help")
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_short_flag(self):
        result = run_install("-h")
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_shows_local_flag(self):
        result = run_install("--help")
        assert "--local" in result.stdout

    def test_help_shows_no_start_flag(self):
        result = run_install("--help")
        assert "--no-start" in result.stdout

    def test_unknown_flag_exits_nonzero(self):
        result = run_install("--bogus")
        assert result.returncode == 1
        assert "Unknown option" in result.stderr

    def test_dir_flag_with_space(self, tmp_path):
        result = run_install("--dry-run", "--dir", str(tmp_path / "custom"))
        assert result.returncode == 0

    def test_dir_flag_equals_syntax(self, tmp_path):
        result = run_install("--dry-run", f"--dir={tmp_path / 'custom'}")
        assert result.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# Docker Default Mode
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestDockerDefault:
    """Tests for Docker-first default installation mode."""

    def test_default_requires_docker(self, stubbed_env):
        """Without docker, default mode should fail."""
        env = _env_without_stub(stubbed_env, "docker")
        result = run_install(env=env)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "Docker is required" in output

    def test_default_checks_docker_running(self, stubbed_env):
        """Docker present but not running should fail."""
        bin_dir = stubbed_env["PATH"].split(":")[0]
        docker_stub = Path(bin_dir) / "docker"
        docker_stub.write_text(
            '#!/bin/bash\n'
            'if [[ "$1" == "info" ]]; then exit 1; fi\n'
            'if [[ "$1" == "--version" ]]; then echo "Docker version 24.0.0"; fi\n'
            'exit 0\n'
        )
        docker_stub.chmod(0o755)
        result = run_install(env=stubbed_env)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "not running" in output.lower()

    def test_default_dry_run_shows_compose_up(self, stubbed_env):
        """Dry run should show docker compose up command."""
        result = run_install("--dry-run", env=stubbed_env)
        assert result.returncode == 0
        assert "docker compose" in result.stdout
        assert "up -d --build" in result.stdout

    def test_default_skips_venv(self, stubbed_env, install_dir):
        """Docker mode should not create a .venv directory."""
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert not (install_dir / ".venv").exists()

    def test_default_prints_dashboard_url(self, stubbed_env):
        """Docker mode completion message should mention localhost:3000."""
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert "localhost:3000" in result.stdout

    def test_no_start_skips_compose(self, stubbed_env):
        """--no-start should skip container start."""
        result = run_install("--no-start", env=stubbed_env)
        assert result.returncode == 0
        assert "Skipping container start" in result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Local Mode
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestLocalMode:
    """Tests for --local development mode."""

    def test_local_creates_venv(self, stubbed_env, install_dir):
        """--local should create a .venv directory."""
        result = run_install("--local", env=stubbed_env)
        assert result.returncode == 0
        assert (install_dir / ".venv").is_dir()

    def test_local_installs_frontend_deps(self, stubbed_env, install_dir):
        """--local --dry-run should show npm install."""
        # Create frontend directory so setup_frontend finds it
        (install_dir / "tools" / "dashboard" / "frontend").mkdir(parents=True)
        result = run_install("--local", "--dry-run", env=stubbed_env)
        assert result.returncode == 0
        assert "npm" in result.stdout

    def test_local_docker_optional(self, stubbed_env):
        """--local mode should succeed even without docker."""
        env = _env_without_stub(stubbed_env, "docker")
        result = run_install("--local", env=env)
        assert result.returncode == 0

    def test_local_requires_node(self, stubbed_env):
        """--local mode should fail without node."""
        env = _env_without_stub(stubbed_env, "node")
        result = run_install("--local", env=env)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "node" in output.lower()

    def test_local_requires_python(self, stubbed_env):
        """--local mode should fail without python3."""
        env = _env_without_stub(stubbed_env, "python3")
        result = run_install("--local", env=env)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "python" in output.lower()

    def test_local_prints_dev_script_hint(self, stubbed_env):
        """--local completion message should mention scripts/dev.sh."""
        result = run_install("--local", env=stubbed_env)
        assert result.returncode == 0
        assert "scripts/dev.sh" in result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Dry Run
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestDryRun:
    """Tests for --dry-run mode."""

    def test_dry_run_creates_no_files(self, tmp_path):
        target = tmp_path / "dryrun_target"
        before = set(tmp_path.rglob("*"))
        run_install("--dry-run", f"--dir={target}")
        after = set(tmp_path.rglob("*"))
        assert before == after

    def test_dry_run_output_shows_would_do(self, stubbed_env):
        result = run_install("--dry-run", env=stubbed_env)
        assert "[DRY-RUN]" in result.stdout

    def test_dry_run_exits_zero(self, stubbed_env):
        result = run_install("--dry-run", env=stubbed_env)
        assert result.returncode == 0

    def test_dry_run_reports_completion(self, stubbed_env):
        result = run_install("--dry-run", env=stubbed_env)
        assert "Dry run complete" in result.stdout

    def test_dry_run_local_mode(self, stubbed_env):
        """--local --dry-run should succeed without making changes."""
        result = run_install("--local", "--dry-run", env=stubbed_env)
        assert result.returncode == 0
        assert "Dry run complete" in result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Prerequisites
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestPrerequisites:
    """Tests for prerequisite checking with modified stubs."""

    def test_missing_git_shows_install_hint(self, stubbed_env):
        env = _env_without_stub(stubbed_env, "git")
        result = run_install(env=env)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "git" in output.lower()

    def test_missing_curl_fails(self, stubbed_env):
        env = _env_without_stub(stubbed_env, "curl")
        result = run_install(env=env)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "curl" in output.lower()

    def test_docker_required_in_default_mode(self, stubbed_env):
        """Docker is required in default (Docker) mode."""
        env = _env_without_stub(stubbed_env, "docker")
        result = run_install(env=env)
        assert result.returncode == 1

    def test_docker_optional_in_local_mode(self, stubbed_env):
        """Docker is optional in --local mode."""
        env = _env_without_stub(stubbed_env, "docker")
        result = run_install("--local", env=env)
        assert result.returncode == 0

    def test_python_required_in_local_mode(self, stubbed_env):
        """Python is required in --local mode."""
        env = _env_without_stub(stubbed_env, "python3")
        result = run_install("--local", env=env)
        assert result.returncode == 1

    def test_python_not_required_in_docker_mode(self, stubbed_env):
        """Python is NOT required in Docker mode."""
        env = _env_without_stub(stubbed_env, "python3")
        result = run_install(env=env)
        assert result.returncode == 0

    def test_old_python_version_rejected_local(self, stubbed_env):
        """Python 3.9 should be rejected in local mode (minimum is 3.11)."""
        bin_dir = stubbed_env["PATH"].split(":")[0]
        old_python = Path(bin_dir) / "python3"
        old_python.write_text(
            '#!/bin/bash\n'
            'if [[ "$*" == *"sys.version_info"* ]]; then\n'
            '    echo "3.9"\n'
            'else\n'
            '    exit 0\n'
            'fi\n'
        )
        old_python.chmod(0o755)
        result = run_install("--local", env=stubbed_env)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "3.11" in output or "required" in output.lower()


# ─────────────────────────────────────────────────────────────────────────────
# version_gte function
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestVersionGte:
    """Tests for the version_gte bash function."""

    @pytest.mark.parametrize(
        ("version", "minimum", "expected_rc"),
        [
            ("3.12", "3.11", 0),  # greater
            ("3.11", "3.11", 0),  # equal
            ("3.10", "3.11", 1),  # less
        ],
    )
    def test_version_comparison_cases(self, version, minimum, expected_rc):
        """Test version_gte using a small bash snippet calling the function directly."""
        snippet = f"""
version_gte() {{
    printf '%s\\n%s\\n' "$2" "$1" | sort -V -C
}}
version_gte '{version}' '{minimum}'
"""
        result = subprocess.run(
            ["bash", "-c", snippet],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == expected_rc


# ─────────────────────────────────────────────────────────────────────────────
# .env File
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestEnvFile:
    """Tests for .env file creation and handling."""

    def test_creates_env_from_example(self, stubbed_env, install_dir):
        """When .env.example exists and .env does not, .env should be created."""
        assert not (install_dir / ".env").exists()
        assert (install_dir / ".env.example").exists()
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert (install_dir / ".env").exists()

    def test_preserves_existing_env(self, stubbed_env, install_dir):
        """An existing .env should not be overwritten (but master key may be updated)."""
        custom_content = "MY_CUSTOM_VAR=keep_this\nDEXAI_MASTER_KEY=already-set-key\n"
        env_file = install_dir / ".env"
        env_file.write_text(custom_content)
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        content = env_file.read_text()
        assert "MY_CUSTOM_VAR=keep_this" in content
        assert "DEXAI_MASTER_KEY=already-set-key" in content

    def test_env_permissions_600(self, stubbed_env, install_dir):
        """New .env should have 600 permissions."""
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        env_file = install_dir / ".env"
        if env_file.exists():
            mode = stat.S_IMODE(os.stat(env_file).st_mode)
            assert mode == 0o600

    def test_creates_empty_env_without_example(self, stubbed_env, install_dir):
        """Without .env.example, .env should still be created (via touch)."""
        example = install_dir / ".env.example"
        if example.exists():
            example.unlink()
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert (install_dir / ".env").exists()


# ─────────────────────────────────────────────────────────────────────────────
# Master Key Generation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestMasterKeyGeneration:
    """Tests for DEXAI_MASTER_KEY auto-generation."""

    def test_master_key_auto_generated(self, stubbed_env, install_dir):
        """Placeholder master key should be replaced with a generated value."""
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        env_file = install_dir / ".env"
        content = env_file.read_text()
        # Should no longer have the placeholder
        assert "your-secure-master-password-here" not in content
        # Should have a DEXAI_MASTER_KEY line with a non-empty value
        for line in content.splitlines():
            if line.startswith("DEXAI_MASTER_KEY="):
                key_value = line.split("=", 1)[1]
                assert len(key_value) > 0
                assert key_value != "your-secure-master-password-here"
                break
        else:
            pytest.fail("DEXAI_MASTER_KEY not found in .env")

    def test_master_key_preserved_if_already_set(self, stubbed_env, install_dir):
        """An already-set master key should not be overwritten."""
        env_file = install_dir / ".env"
        env_file.write_text("DEXAI_MASTER_KEY=my-real-secret-key-12345\n")
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        content = env_file.read_text()
        assert "DEXAI_MASTER_KEY=my-real-secret-key-12345" in content

    def test_master_key_uses_openssl(self, stubbed_env, install_dir):
        """The openssl stub output should appear as the generated key."""
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        env_file = install_dir / ".env"
        content = env_file.read_text()
        # Our openssl stub returns the deterministic hex string
        assert "abcdef1234567890" in content


# ─────────────────────────────────────────────────────────────────────────────
# Data Directories
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestDataDirectories:
    """Tests for data directory creation."""

    def test_creates_data_directory(self, stubbed_env, install_dir):
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert (install_dir / "data").is_dir()

    def test_creates_memory_logs(self, stubbed_env, install_dir):
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert (install_dir / "memory" / "logs").is_dir()

    def test_data_dir_permissions_700(self, stubbed_env, install_dir):
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        data_dir = install_dir / "data"
        if data_dir.exists():
            mode = stat.S_IMODE(os.stat(data_dir).st_mode)
            assert mode == 0o700

    def test_idempotent_on_existing_dirs(self, stubbed_env, install_dir):
        """Pre-creating dirs should not cause errors on re-run."""
        (install_dir / "data").mkdir(exist_ok=True)
        (install_dir / "memory" / "logs").mkdir(parents=True, exist_ok=True)
        result = run_install(env=stubbed_env)
        assert result.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# Color / ANSI Output
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestColorOutput:
    """Tests for color/ANSI handling."""

    def test_no_ansi_in_non_terminal(self, stubbed_env):
        """subprocess is non-tty, so no ANSI escape codes should appear."""
        result = run_install(env=stubbed_env)
        combined = result.stdout + result.stderr
        assert "\033[" not in combined


# ─────────────────────────────────────────────────────────────────────────────
# Full Run — Docker
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestFullRunDocker:
    """End-to-end tests for Docker mode (default)."""

    def test_full_docker_run_succeeds(self, stubbed_env):
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert "DexAI is running" in result.stdout

    def test_full_docker_run_creates_expected_structure(self, stubbed_env, install_dir):
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert (install_dir / ".env").exists()
        assert (install_dir / "data").is_dir()
        assert (install_dir / "memory" / "logs").is_dir()
        # Docker mode should NOT create .venv
        assert not (install_dir / ".venv").exists()

    def test_full_docker_shows_add_later_hints(self, stubbed_env):
        """Completion message should show how to add Caddy and Tailscale later."""
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        assert "--with-proxy" in result.stdout
        assert "--with-tailscale" in result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Full Run — Local
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestFullRunLocal:
    """End-to-end tests for --local mode."""

    def test_full_local_run_succeeds(self, stubbed_env):
        result = run_install("--local", env=stubbed_env)
        assert result.returncode == 0
        assert "Local setup complete" in result.stdout

    def test_full_local_run_creates_expected_structure(self, stubbed_env, install_dir):
        result = run_install("--local", env=stubbed_env)
        assert result.returncode == 0
        assert (install_dir / ".env").exists()
        assert (install_dir / "data").is_dir()
        assert (install_dir / "memory" / "logs").is_dir()
        # Local mode should create .venv
        assert (install_dir / ".venv").is_dir()


# ─────────────────────────────────────────────────────────────────────────────
# Optional Service Profiles (--with-proxy, --with-tailscale)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.install
class TestOptionalProfiles:
    """Tests for --with-proxy and --with-tailscale flags."""

    def test_help_shows_profile_flags(self):
        result = run_install("--help")
        assert "--with-proxy" in result.stdout
        assert "--with-tailscale" in result.stdout

    def test_with_proxy_includes_profile_in_compose(self, stubbed_env):
        """--with-proxy should pass --profile proxy to docker compose."""
        result = run_install("--with-proxy", "--dry-run", env=stubbed_env)
        assert result.returncode == 0
        assert "--profile proxy" in result.stdout

    def test_with_tailscale_includes_profile_in_compose(self, stubbed_env):
        """--with-tailscale should pass --profile tailscale to docker compose."""
        result = run_install("--with-tailscale", "--dry-run", env=stubbed_env)
        assert result.returncode == 0
        assert "--profile tailscale" in result.stdout

    def test_both_profiles_combined(self, stubbed_env):
        """Both --with-proxy and --with-tailscale can be combined."""
        result = run_install("--with-proxy", "--with-tailscale", "--dry-run", env=stubbed_env)
        assert result.returncode == 0
        assert "--profile proxy" in result.stdout
        assert "--profile tailscale" in result.stdout

    def test_with_proxy_sets_domain_in_env(self, stubbed_env, install_dir):
        """--with-proxy should set DEXAI_DOMAIN in .env (non-interactive uses existing)."""
        result = run_install("--with-proxy", env=stubbed_env)
        assert result.returncode == 0
        env_file = install_dir / ".env"
        content = env_file.read_text()
        # Domain should be set (either from .env.example default or kept)
        assert "DEXAI_DOMAIN=" in content

    def test_with_proxy_hides_proxy_add_later_hint(self, stubbed_env):
        """When --with-proxy is active, don't show 'add proxy later' hint."""
        result = run_install("--with-proxy", env=stubbed_env)
        assert result.returncode == 0
        # Should NOT show the --with-proxy add-later hint
        assert "bash install.sh --with-proxy" not in result.stdout

    def test_with_tailscale_hides_tailscale_add_later_hint(self, stubbed_env):
        """When --with-tailscale is active, don't show 'add tailscale later' hint."""
        result = run_install("--with-tailscale", env=stubbed_env)
        assert result.returncode == 0
        assert "bash install.sh --with-tailscale" not in result.stdout

    def test_interactive_prompts_skipped_in_subprocess(self, stubbed_env):
        """In non-tty (subprocess), interactive prompts should be skipped."""
        # subprocess is always non-tty, so prompts should never appear
        result = run_install(env=stubbed_env)
        assert result.returncode == 0
        # Should not contain prompt text (prompts require tty)
        assert "Enable HTTPS via Caddy" not in result.stdout

    def test_profiles_not_available_in_local_mode(self, stubbed_env):
        """--local mode should mention Docker for HTTPS/Tailscale."""
        result = run_install("--local", env=stubbed_env)
        assert result.returncode == 0
        assert "Docker mode" in result.stdout or "install.sh --with-proxy" in result.stdout
