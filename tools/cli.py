#!/usr/bin/env python3
"""
DexAI Command Line Interface

Main entry point for the `dexai` command.

Usage:
    dexai setup              # Launch setup wizard (TUI)
    dexai setup --web        # Open web-based setup wizard
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
    """Handle setup subcommand."""
    from tools.setup.tui.main import main as tui_main

    # Build args for the TUI main
    sys.argv = ["dexai-setup"]
    if args.resume:
        sys.argv.append("--resume")
    if args.reset:
        sys.argv.append("--reset")
    if args.web:
        sys.argv.append("--web")
    if args.status:
        sys.argv.append("--status")

    tui_main()


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
        "setup", help="Launch the setup wizard"
    )
    setup_parser.add_argument(
        "--web", action="store_true", help="Open web-based wizard instead of TUI"
    )
    setup_parser.add_argument(
        "--resume", action="store_true", help="Resume previous setup"
    )
    setup_parser.add_argument(
        "--reset", action="store_true", help="Reset setup state and start fresh"
    )
    setup_parser.add_argument(
        "--status", action="store_true", help="Show current setup status"
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
    args.func(args)


if __name__ == "__main__":
    main()
