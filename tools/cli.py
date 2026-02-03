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
