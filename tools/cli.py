#!/usr/bin/env python3
"""
DexAI Command Line Interface

Main entry point for the `dexai` command.

Usage:
    dexai setup --status     # Show setup status
    dexai setup --reset      # Reset setup state
    dexai dashboard          # Start the dashboard server
    dexai --version          # Show version
"""

import argparse
import sys
from pathlib import Path


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def cmd_setup(args):
    """Handle setup subcommand.

    With no flags, runs an interactive setup wizard that walks through
    vault init, API key configuration, database migration, and channel
    setup.  Uses shared functions from ``tools.setup.setup_core`` so the
    dashboard chat can call the same logic.
    """
    import json

    from tools.setup.setup_core import (
        check_prerequisites,
        configure_api_keys,
        configure_channel,
        get_setup_status,
        init_vault,
        run_migrations,
        verify_installation,
    )

    # --status: print JSON status and exit
    if args.status:
        print(json.dumps(get_setup_status(), indent=2))
        return

    # --verify: run post-setup verification
    if args.verify:
        result = verify_installation()
        if result["success"]:
            print("All checks passed.")
        else:
            print("Some checks failed:")
            for w in result.get("warnings", []):
                print(f"  - {w}")
        return 0 if result["success"] else 1

    # --reset: clear setup state
    if args.reset:
        from tools.setup.wizard import reset_setup
        result = reset_setup()
        print("Setup state reset." if result.get("success") else f"Error: {result}")
        return

    # ---------------------------------------------------------------
    # Interactive setup wizard
    # ---------------------------------------------------------------
    _run_setup_wizard(
        check_prerequisites=check_prerequisites,
        init_vault=init_vault,
        configure_api_keys=configure_api_keys,
        configure_channel=configure_channel,
        run_migrations=run_migrations,
        verify_installation=verify_installation,
        get_setup_status=get_setup_status,
    )


def _run_setup_wizard(
    *,
    check_prerequisites,
    init_vault,
    configure_api_keys,
    configure_channel,
    run_migrations,
    verify_installation,
    get_setup_status,
):
    """Interactive CLI setup wizard.

    Thin UI layer that prompts the user and delegates to shared setup_core
    functions.  Designed to be easily removable once the dashboard chat
    covers all setup steps.
    """
    import getpass
    import os

    # Helpers for consistent output
    def _header(title: str) -> None:
        print(f"\n{'=' * 50}")
        print(f"  {title}")
        print(f"{'=' * 50}\n")

    def _step_ok(msg: str) -> None:
        print(f"  [OK] {msg}")

    def _step_fail(msg: str) -> None:
        print(f"  [!!] {msg}")

    def _prompt(label: str, default: str = "", secret: bool = False) -> str:
        suffix = f" [{default}]" if default else ""
        prompt_text = f"  {label}{suffix}: "
        if secret:
            value = getpass.getpass(prompt_text)
        else:
            try:
                value = input(prompt_text)
            except EOFError:
                value = ""
        return value.strip() or default

    # ------------------------------------------------------------------
    _header("DexAI Setup Wizard")
    print("This wizard will configure your DexAI installation.")
    print("You can re-run it at any time with: dexai setup")
    print("Or complete setup via the dashboard: dexai dashboard\n")

    # Step 1: Prerequisites
    _header("Step 1/5 — Prerequisites")
    prereq = check_prerequisites()
    for check in prereq["checks"]:
        status = "OK" if check["ok"] else "MISSING"
        optional = " (optional)" if check.get("optional") else ""
        print(f"  [{status}] {check['name']}{optional}")
    if not prereq["success"]:
        print(f"\nMissing prerequisites: {', '.join(prereq['missing'])}")
        print("Please install them and re-run: dexai setup")
        return

    # Step 2: Vault / Master Key
    _header("Step 2/5 — Vault Initialization")
    master_key = os.environ.get("DEXAI_MASTER_KEY", "")
    placeholder = master_key == "your-secure-master-password-here"
    if master_key and not placeholder:
        _step_ok("Master key already configured")
        vault_result = init_vault(master_key)
    else:
        print("  A master key encrypts all stored secrets.")
        print("  Press Enter to auto-generate a secure key (recommended).\n")
        user_key = _prompt("Master key (or Enter to generate)", secret=True)
        vault_result = init_vault(user_key)
        if vault_result["success"]:
            if vault_result.get("generated_key"):
                _step_ok("Secure master key generated and saved to .env")
            else:
                _step_ok("Master key saved to .env")
        else:
            _step_fail(f"Vault init failed: {vault_result.get('error')}")
            return

    # Step 3: API Keys
    _header("Step 3/5 — API Keys")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    anthropic_placeholder = anthropic_key.startswith("sk-ant-your-")
    if anthropic_key and not anthropic_placeholder:
        _step_ok("Anthropic API key already configured")
    else:
        print("  Get your key at: https://console.anthropic.com/")
        anthropic_key = _prompt("Anthropic API key (sk-ant-...)", secret=True)
        if not anthropic_key:
            print("  Skipping — you can add this later via .env or dexai setup")

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_placeholder = openai_key.startswith("sk-your-")
    if openai_key and not openai_placeholder:
        _step_ok("OpenAI API key already configured")
    else:
        openai_key = _prompt("OpenAI API key (optional, for embeddings)", secret=True)

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        _step_ok("OpenRouter API key already configured")
    else:
        openrouter_key = _prompt("OpenRouter API key (optional, for model routing)", secret=True)

    if anthropic_key and not anthropic_placeholder:
        api_result = configure_api_keys(
            anthropic_key=anthropic_key,
            openai_key=openai_key if openai_key and not openai_placeholder else None,
            openrouter_key=openrouter_key or None,
        )
        if api_result["success"]:
            _step_ok(f"Stored: {', '.join(api_result['stored'])}")
        else:
            for err in api_result.get("errors", []):
                _step_fail(err)

    # Step 4: Database Initialization
    _header("Step 4/5 — Database Initialization")
    mig_result = run_migrations()
    if mig_result["success"]:
        _step_ok(f"Initialized: {', '.join(mig_result['initialized'])}")
    else:
        for err in mig_result.get("errors", []):
            _step_fail(err)

    # Step 5: Channel Setup (optional)
    _header("Step 5/5 — Messaging Channel (optional)")
    print("  Configure a messaging channel to chat with DexAI.")
    print("  You can skip this and configure later.\n")
    print("  1) Telegram")
    print("  2) Discord")
    print("  3) Slack")
    print("  4) Skip for now\n")

    choice = _prompt("Choose a channel [4]", default="4")
    channel_map = {"1": "telegram", "2": "discord", "3": "slack"}

    if choice in channel_map:
        ch_name = channel_map[choice]
        token = _prompt(f"  {ch_name.title()} bot token", secret=True)
        if token:
            extra_kwargs = {}
            if ch_name == "slack":
                app_token = _prompt("  Slack app token (xapp-...)", secret=True)
                if app_token:
                    extra_kwargs["app_token"] = app_token
            ch_result = configure_channel(ch_name, token, **extra_kwargs)
            if ch_result["success"]:
                _step_ok(f"{ch_name.title()} configured")
            else:
                for err in ch_result.get("errors", []):
                    _step_fail(err)
        else:
            print("  Skipped — no token provided.")
    else:
        print("  Skipped channel setup.")

    # Verification
    _header("Verification")
    verify = verify_installation()
    for check in verify["checks"]:
        status = "OK" if check["ok"] else "WARN"
        print(f"  [{status}] {check['name']}")
    for w in verify.get("warnings", []):
        print(f"  [!!] {w}")

    # Summary
    status = get_setup_status()
    _header("Setup Complete")
    if status["complete"]:
        print("  All setup steps are done. You are ready to go!")
    else:
        print("  Remaining steps:")
        for item in status.get("missing", []):
            print(f"    - {item}")

    print("\n  Start the dashboard:  dexai dashboard")
    print("  Re-run setup:         dexai setup")
    print("  Run diagnostics:      dexai doctor\n")


def cmd_dashboard(args):
    """Handle dashboard subcommand."""
    import uvicorn

    host = args.host or "127.0.0.1"
    port = args.port or 8080

    print(f"Starting DexAI Dashboard at http://{host}:{port}")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        "tools.dashboard.backend.main:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def cmd_version(args):
    """Show version information."""
    try:
        from importlib.metadata import version

        v = version("dexai")
    except Exception:
        v = "0.1.0 (development)"

    print(f"DexAI version {v}")


def cmd_doctor(args):
    """Run diagnostic checks on the DexAI installation.

    Checks Python version, dependencies, vault, databases, environment
    variables, disk space, Docker, API connectivity, migrations, and
    channel tokens.  Returns exit code 0 if all critical checks pass.
    """
    import logging
    import os
    import shutil
    import sqlite3
    import sys

    logger = logging.getLogger("dexai.doctor")

    checks_passed = 0
    checks_failed = 0
    checks_warned = 0

    def _pass(msg: str) -> None:
        nonlocal checks_passed
        checks_passed += 1
        print(f"  \u2713 {msg}")

    def _fail(msg: str) -> None:
        nonlocal checks_failed
        checks_failed += 1
        print(f"  \u2717 {msg}")

    def _warn(msg: str) -> None:
        nonlocal checks_warned
        checks_warned += 1
        print(f"  ! {msg}")

    print("DexAI Doctor")
    print("=" * 50)

    # 1. Python version
    print("\n[Python Version]")
    v = sys.version_info
    if v >= (3, 11):
        _pass(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro} (requires >= 3.11)")

    # 2. Dependencies
    print("\n[Dependencies]")
    required_packages = [
        "anthropic",
        "fastapi",
        "httpx",
        "uvicorn",
        "yaml",
        "rich",
    ]
    optional_packages = [
        ("aiohttp", "office integration"),
        ("PIL", "multi-modal (Pillow)"),
        ("PyPDF2", "PDF extraction"),
        ("docx", "Word document parsing"),
        ("openai", "DALL-E / embeddings"),
        ("docker", "container isolation"),
    ]
    for pkg in required_packages:
        try:
            __import__(pkg)
            _pass(f"{pkg}")
        except ImportError:
            _fail(f"{pkg} -- missing (required)")

    for pkg, purpose in optional_packages:
        try:
            __import__(pkg)
            _pass(f"{pkg} ({purpose})")
        except ImportError:
            _warn(f"{pkg} -- not installed ({purpose})")

    # 3. Vault health
    print("\n[Vault Health]")
    vault_path = PROJECT_ROOT / "data" / "vault.db"
    master_key = os.environ.get("DEXAI_MASTER_KEY")
    if not master_key:
        _fail("DEXAI_MASTER_KEY not set -- vault cannot operate")
    elif not vault_path.exists():
        _warn("Vault database not found (will be created on first use)")
    else:
        try:
            from tools.security import vault as _vault
            _vault.get_secret("__doctor_probe__", namespace="doctor")
            # If it returns (even with success=False for missing key), vault is reachable
            _pass("Vault accessible and decryptable")
        except Exception as exc:
            _fail(f"Vault error: {exc}")

    # 4. Database health
    print("\n[Database Health]")
    db_checks = {
        "memory.db": PROJECT_ROOT / "data" / "memory.db",
        "activity.db": PROJECT_ROOT / "data" / "activity.db",
        "audit.db": PROJECT_ROOT / "data" / "audit.db",
    }
    for name, db_path in db_checks.items():
        if not db_path.exists():
            _warn(f"{name} not found at {db_path}")
        else:
            try:
                conn = sqlite3.connect(str(db_path))
                conn.execute("SELECT 1")
                conn.close()
                _pass(f"{name} accessible")
            except Exception as exc:
                _fail(f"{name} error: {exc}")

    # 5. Environment variables
    print("\n[Environment Variables]")
    required_vars = ["DEXAI_MASTER_KEY", "ANTHROPIC_API_KEY"]
    optional_vars = [
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "HELICONE_API_KEY",
    ]
    for var in required_vars:
        if os.environ.get(var):
            _pass(f"{var} is set")
        else:
            _fail(f"{var} is NOT set (required)")

    for var in optional_vars:
        if os.environ.get(var):
            _pass(f"{var} is set")
        else:
            _warn(f"{var} is not set (optional)")

    # 6. Disk space
    print("\n[Disk Space]")
    try:
        usage = shutil.disk_usage(str(PROJECT_ROOT))
        free_mb = usage.free / (1024 * 1024)
        if free_mb > 100:
            _pass(f"{free_mb:.0f} MB free")
        else:
            _fail(f"Only {free_mb:.0f} MB free (need > 100 MB)")
    except Exception as exc:
        _warn(f"Could not check disk space: {exc}")

    # 7. Docker
    print("\n[Docker]")
    try:
        import subprocess

        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            _pass("Docker daemon is running")
        else:
            _warn("Docker daemon not reachable (optional, needed for container isolation)")
    except FileNotFoundError:
        _warn("Docker CLI not found (optional)")
    except Exception as exc:
        _warn(f"Docker check failed: {exc}")

    # 8. API connectivity
    print("\n[API Connectivity]")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _warn("Skipped Anthropic API ping (no API key)")
    else:
        try:
            import httpx

            resp = httpx.head(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            # 401/403 still means reachable; only network errors are failures
            if resp.status_code < 500:
                _pass(f"Anthropic API reachable (HTTP {resp.status_code})")
            else:
                _fail(f"Anthropic API returned HTTP {resp.status_code}")
        except Exception as exc:
            _fail(f"Anthropic API unreachable: {exc}")

    # 9. Migration status
    print("\n[Migration Status]")
    try:
        from tools.ops.migrate import pending_migrations

        pending = pending_migrations()
        if pending:
            _warn(f"{len(pending)} pending migration(s): {', '.join(p.name for p in pending)}")
        else:
            _pass("All migrations applied")
    except Exception as exc:
        _warn(f"Could not check migrations: {exc}")

    # 10. Channel tokens
    print("\n[Channel Tokens]")
    channel_vars = {
        "TELEGRAM_BOT_TOKEN": "Telegram",
        "DISCORD_BOT_TOKEN": "Discord",
        "SLACK_BOT_TOKEN": "Slack",
    }
    any_channel = False
    for var, name in channel_vars.items():
        if os.environ.get(var):
            _pass(f"{name} token is set")
            any_channel = True
        else:
            _warn(f"{name} token not set (optional)")

    if not any_channel:
        _warn("No channel tokens configured -- messaging channels will be unavailable")

    # Summary
    print("\n" + "=" * 50)
    print(f"Results: {checks_passed} passed, {checks_failed} failed, {checks_warned} warnings")

    if checks_failed == 0:
        print("\nAll critical checks passed.")
    else:
        print(f"\n{checks_failed} critical check(s) failed. Please fix the issues above.")

    return checks_failed


def cmd_skill(args):
    """Handle skill subcommand."""
    import json

    from tools.agent.skill_validator import validate_skill, test_skill, list_skills

    if args.skill_command == "validate":
        result = validate_skill(args.name)
        output = result.to_dict()
        output["skill_name"] = args.name

        if result.valid:
            print(f"Skill '{args.name}' is valid.")
        else:
            print(f"Skill '{args.name}' has {len(result.errors)} error(s).")

        if result.errors:
            print("\nErrors:")
            for err in result.errors:
                print(f"  - {err}")
        if result.warnings:
            print("\nWarnings:")
            for warn in result.warnings:
                print(f"  - {warn}")
        if result.info and args.verbose:
            print("\nInfo:")
            for info in result.info:
                print(f"  - {info}")

        if not result.valid:
            return 1

    elif args.skill_command == "test":
        result = test_skill(args.name, dry_run=not args.live)
        passed = result.get("tests_passed", 0)
        total = result.get("tests_total", 0)

        print(f"Testing skill '{args.name}' ({'live' if args.live else 'dry run'})")
        print(f"Results: {passed}/{total} tests passed\n")

        for tr in result.get("test_results", []):
            status = "PASS" if tr["passed"] else "FAIL"
            print(f"  [{status}] {tr['test']}: {tr['detail']}")

        if not result.get("success"):
            validation = result.get("validation", {})
            if validation.get("errors"):
                print("\nValidation errors:")
                for err in validation["errors"]:
                    print(f"  - {err}")
            return 1

    elif args.skill_command == "list":
        skills = list_skills(args.dir)

        if not skills:
            print("No skills found.")
            return

        # Table header
        print(f"{'Name':<30} {'Valid':<7} {'Errors':<8} {'Warnings':<10} {'Description'}")
        print("-" * 90)

        for skill in skills:
            valid_str = "yes" if skill["valid"] else "NO"
            desc = skill.get("description", "") or ""
            if isinstance(desc, str) and len(desc) > 40:
                desc = desc[:37] + "..."
            # Flatten multiline descriptions
            desc = " ".join(desc.split())
            print(
                f"{skill['name']:<30} {valid_str:<7} "
                f"{skill['error_count']:<8} {skill['warning_count']:<10} "
                f"{desc}"
            )

        print(f"\nTotal: {len(skills)} skill(s)")

    else:
        print("Unknown skill command. Use --help for available commands.")
        return 1


def cmd_memory(args):
    """Handle memory subcommand."""
    import asyncio

    async def run_memory_command():
        if args.memory_command == "check":
            return await cmd_memory_check(args)
        elif args.memory_command == "status":
            return await cmd_memory_status(args)
        elif args.memory_command == "deploy":
            return await cmd_memory_deploy(args)
        elif args.memory_command == "migrate":
            return await cmd_memory_migrate(args)
        elif args.memory_command == "setup":
            return await cmd_memory_setup(args)
        else:
            print("Unknown memory command. Use --help for available commands.")
            return 1

    return asyncio.run(run_memory_command())


async def cmd_memory_check(args):
    """Check memory provider dependencies."""
    from tools.memory.service import MemoryService

    print("Checking memory provider dependencies...\n")

    service = MemoryService()
    status = await service.check_dependencies()

    print(f"Provider: {service.provider.name}")
    print(f"Mode: {service.provider.deployment_mode.value}")
    print(f"Ready: {'Yes' if status.ready else 'No'}")
    print()

    print("Dependencies:")
    for dep, available in status.dependencies.items():
        icon = "✓" if available else "✗"
        print(f"  {icon} {dep}")

    if status.missing:
        print(f"\nMissing: {', '.join(status.missing)}")

    if status.instructions:
        print(f"\nSetup instructions:\n{status.instructions}")

    return 0 if status.ready else 1


async def cmd_memory_status(args):
    """Show memory service status."""
    from tools.memory.service import MemoryService

    print("Memory Service Status\n" + "=" * 40)

    try:
        service = MemoryService()
        await service.initialize()

        health = await service.health_check()

        print(f"Provider: {health.provider}")
        print(f"Healthy: {'Yes' if health.healthy else 'No'}")
        print(f"Latency: {health.latency_ms:.2f}ms")

        if health.details:
            print("\nDetails:")
            for key, value in health.details.items():
                print(f"  {key}: {value}")

        # Get stats
        stats = await service.get_stats()
        print(f"\nStatistics:")
        print(f"  Total memories: {stats.get('total', 0)}")
        if stats.get('by_type'):
            print(f"  By type: {stats['by_type']}")
        if stats.get('active_commitments'):
            print(f"  Active commitments: {stats['active_commitments']}")

        return 0 if health.healthy else 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


async def cmd_memory_deploy(args):
    """Deploy local development dependencies."""
    from tools.memory.service import MemoryService

    print("Deploying local memory dependencies...\n")

    service = MemoryService()

    try:
        result = await service.deploy_local()

        print(f"Success: {result.success}")
        print(f"Message: {result.message}")

        if result.services:
            print("\nServices:")
            for name, url in result.services.items():
                print(f"  {name}: {url}")

        return 0 if result.success else 1

    except NotImplementedError as e:
        print(f"Not supported: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


async def cmd_memory_migrate(args):
    """Migrate data between providers."""
    print("Memory Migration")
    print("=" * 40)

    if not args.source or not args.target:
        print("Error: --source and --target are required")
        print("Example: dexai memory migrate --source native --target mem0")
        return 1

    from tools.memory.providers import get_provider

    print(f"Source: {args.source}")
    print(f"Target: {args.target}")
    print()

    if args.dry_run:
        print("DRY RUN - no data will be migrated\n")

    try:
        # Initialize providers
        source_provider = get_provider(args.source)
        target_provider = get_provider(args.target)

        # Check dependencies
        source_status = await source_provider.check_dependencies()
        if not source_status.ready:
            print(f"Source provider not ready: {source_status.missing}")
            return 1

        target_status = await target_provider.check_dependencies()
        if not target_status.ready:
            print(f"Target provider not ready: {target_status.missing}")
            return 1

        # Bootstrap target
        await target_provider.bootstrap()

        # Get entries from source
        entries = await source_provider.list(limit=10000)
        print(f"Found {len(entries)} entries to migrate")

        if args.dry_run:
            print("\nDry run complete. Use without --dry-run to migrate.")
            return 0

        # Migrate entries
        migrated = 0
        failed = 0

        for entry in entries:
            try:
                await target_provider.add(
                    content=entry.content,
                    type=entry.type,
                    importance=entry.importance,
                    source=entry.source,
                    tags=entry.tags,
                    metadata=entry.metadata,
                )
                migrated += 1
            except Exception as e:
                failed += 1
                if args.verbose:
                    print(f"  Failed to migrate {entry.id}: {e}")

        print(f"\nMigration complete:")
        print(f"  Migrated: {migrated}")
        print(f"  Failed: {failed}")

        return 0 if failed == 0 else 1

    except Exception as e:
        print(f"Migration error: {e}")
        return 1


async def cmd_memory_setup(args):
    """Interactive memory provider setup."""
    print("Memory Provider Setup")
    print("=" * 40)
    print()
    print("Available providers:")
    print("  1. native     - Local SQLite + hybrid search (default, no dependencies)")
    print("  2. mem0       - Mem0 graph memory (cloud or self-hosted)")
    print("  3. zep        - Zep temporal graph (cloud or self-hosted)")
    print("  4. simplemem  - SimpleMem cloud API")
    print("  5. claudemem  - ClaudeMem local progressive disclosure")
    print()

    # Read current config
    config_path = PROJECT_ROOT / "args" / "memory.yaml"

    if config_path.exists():
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        current = config.get("memory", {}).get("provider", "native")
        print(f"Current provider: {current}")
    else:
        print("No configuration found. Using native provider.")
        current = "native"

    print()
    print("Run 'dexai memory check' to verify dependencies")
    print("Edit args/memory.yaml to change providers")

    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="dexai",
        description="DexAI - Personal AI Assistant for ADHD users",
    )
    parser.add_argument(
        "--version", "-V", action="store_true", help="Show version and exit"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup subcommand
    setup_parser = subparsers.add_parser(
        "setup", help="Interactive setup wizard (or --status / --verify / --reset)"
    )
    setup_parser.add_argument(
        "--reset", action="store_true", help="Reset setup state and start fresh"
    )
    setup_parser.add_argument(
        "--status", action="store_true", help="Show current setup status as JSON"
    )
    setup_parser.add_argument(
        "--verify", action="store_true", help="Run post-setup verification checks"
    )
    setup_parser.set_defaults(func=cmd_setup)

    # Dashboard subcommand
    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Start the dashboard server"
    )
    dashboard_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    dashboard_parser.add_argument(
        "--port", type=int, default=8080, help="Port to bind to (default: 8080)"
    )
    dashboard_parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )
    dashboard_parser.set_defaults(func=cmd_dashboard)

    # Doctor subcommand
    doctor_parser = subparsers.add_parser(
        "doctor", help="Run diagnostic checks on the DexAI installation"
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    # Memory subcommand
    memory_parser = subparsers.add_parser(
        "memory", help="Memory provider management"
    )
    memory_subparsers = memory_parser.add_subparsers(
        dest="memory_command", help="Memory commands"
    )

    # memory check
    memory_check = memory_subparsers.add_parser(
        "check", help="Check memory provider dependencies"
    )
    memory_check.set_defaults(func=cmd_memory)

    # memory status
    memory_status = memory_subparsers.add_parser(
        "status", help="Show memory service status and statistics"
    )
    memory_status.set_defaults(func=cmd_memory)

    # memory deploy
    memory_deploy = memory_subparsers.add_parser(
        "deploy", help="Deploy local development dependencies (e.g., Qdrant container)"
    )
    memory_deploy.set_defaults(func=cmd_memory)

    # memory setup
    memory_setup = memory_subparsers.add_parser(
        "setup", help="Interactive memory provider setup"
    )
    memory_setup.set_defaults(func=cmd_memory)

    # memory migrate
    memory_migrate = memory_subparsers.add_parser(
        "migrate", help="Migrate data between memory providers"
    )
    memory_migrate.add_argument(
        "--source", required=False, help="Source provider (native, mem0, zep, etc.)"
    )
    memory_migrate.add_argument(
        "--target", required=False, help="Target provider (native, mem0, zep, etc.)"
    )
    memory_migrate.add_argument(
        "--dry-run", action="store_true", help="Show what would be migrated without migrating"
    )
    memory_migrate.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed migration progress"
    )
    memory_migrate.set_defaults(func=cmd_memory)

    # Skill subcommand
    skill_parser = subparsers.add_parser(
        "skill", help="Skill validation and management"
    )
    skill_subparsers = skill_parser.add_subparsers(
        dest="skill_command", help="Skill commands"
    )

    # skill validate
    skill_validate = skill_subparsers.add_parser(
        "validate", help="Validate a skill for correctness"
    )
    skill_validate.add_argument(
        "name", help="Skill name (e.g., 'adhd-decomposition') or path"
    )
    skill_validate.add_argument(
        "--verbose", "-v", action="store_true", help="Show info messages"
    )
    skill_validate.set_defaults(func=cmd_skill)

    # skill test
    skill_test = skill_subparsers.add_parser(
        "test", help="Test a skill by parsing and simulating execution"
    )
    skill_test.add_argument(
        "name", help="Skill name (e.g., 'adhd-decomposition') or path"
    )
    skill_test.add_argument(
        "--live", action="store_true", help="Run live test (default: dry run)"
    )
    skill_test.set_defaults(func=cmd_skill)

    # skill list
    skill_list = skill_subparsers.add_parser(
        "list", help="List all available skills with validation status"
    )
    skill_list.add_argument(
        "--dir", default=None, help="Override skills directory to scan"
    )
    skill_list.set_defaults(func=cmd_skill)

    args = parser.parse_args()

    # Handle --version at top level
    if args.version:
        cmd_version(args)
        return

    # If no command given, show help
    if not args.command:
        parser.print_help()
        return

    # Execute command
    result = args.func(args)

    # Commands may return an exit code
    if isinstance(result, int) and result != 0:
        sys.exit(result)


if __name__ == "__main__":
    main()
