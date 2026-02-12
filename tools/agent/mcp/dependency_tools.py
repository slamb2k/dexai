"""
DexAI Dependency MCP Tools

Exposes skill dependency management features as MCP tools for the Claude Agent SDK.
These tools enable the agent to safely install packages when creating skills.

Tools:
- dexai_get_skill_dependency_setting: Get user's install mode preference
- dexai_verify_package: Security check before installing
- dexai_install_package: Install a verified package

Security:
- All packages are verified against known malicious package blocklist
- Typosquatting detection prevents common attack vectors
- Download count verification ensures package legitimacy
- User preference controls whether to ask, auto-install, or block

Usage:
    These tools are registered with the SDK via the agent configuration.
    The SDK agent invokes them when creating skills that need dependencies.
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


def _get_event_loop():
    """Get or create an event loop for async operations."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.new_event_loop()


def _run_async(coro):
    """Run an async coroutine from sync context."""
    loop = _get_event_loop()
    if loop.is_running():
        # We're in an async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


# =============================================================================
# Tool: dexai_get_skill_dependency_setting
# =============================================================================


def dexai_get_skill_dependency_setting(
    user_id: str = "default",
) -> dict[str, Any]:
    """
    Get user's preference for skill dependency installation.

    This should be checked before attempting to install any package.
    The result determines whether to:
    - "ask": Ask the user for permission before installing
    - "always": Proceed with installation after security check
    - "never": Don't install, suggest code-only alternatives

    Args:
        user_id: User to get preference for (default: "default")

    Returns:
        {
            "success": bool,
            "tool": "dexai_get_skill_dependency_setting",
            "mode": "ask" | "always" | "never",
            "description": str  # Human-readable explanation
        }

    Example:
        result = dexai_get_skill_dependency_setting()
        if result["mode"] == "ask":
            # Ask user before installing
        elif result["mode"] == "always":
            # Proceed with security check then install
        else:  # "never"
            # Find code-only alternative
    """
    try:
        from tools.dashboard.backend.database import get_preferences
        from tools.dashboard.backend.routes.settings import load_yaml_config

        # Check user preference first
        prefs = get_preferences(user_id) or {}
        user_mode = prefs.get("skill_dependency_install_mode")

        if user_mode:
            mode = user_mode
        else:
            # Fall back to system config
            config = load_yaml_config("skill_dependencies.yaml")
            mode = config.get("skill_dependencies", {}).get("install_mode", "ask")

        descriptions = {
            "ask": "Ask user for approval before installing packages",
            "always": "Auto-install packages after security verification",
            "never": "Never install packages, suggest code-only alternatives",
        }

        return {
            "success": True,
            "tool": "dexai_get_skill_dependency_setting",
            "mode": mode,
            "description": descriptions.get(mode, "Unknown mode"),
        }

    except ImportError as e:
        logger.warning(f"Dashboard database not available: {e}, defaulting to 'ask'")
        return {
            "success": True,
            "tool": "dexai_get_skill_dependency_setting",
            "mode": "ask",
            "description": "Ask user for approval before installing packages (default)",
        }
    except Exception as e:
        logger.error(f"Failed to get skill dependency setting: {e}")
        return {
            "success": False,
            "tool": "dexai_get_skill_dependency_setting",
            "error": str(e),
            "mode": "ask",  # Safe default
        }


# =============================================================================
# Tool: dexai_verify_package
# =============================================================================


def dexai_verify_package(
    package_name: str,
    version: str | None = None,
) -> dict[str, Any]:
    """
    Verify a package is safe to install.

    Performs security checks including:
    - Package exists on PyPI
    - Not in known malicious packages blocklist
    - Not a typosquat of a popular package
    - Has reasonable download count

    ALWAYS call this before dexai_install_package.

    Args:
        package_name: Name of the package to verify (e.g., "requests", "pyfiglet")
        version: Optional version constraint (e.g., ">=2.0.0")

    Returns:
        {
            "success": bool,
            "tool": "dexai_verify_package",
            "package": str,
            "safe": bool,
            "risk_level": "low" | "medium" | "high" | "blocked",
            "recommendation": "install" | "ask_user" | "skip",
            "warnings": list[str],
            "blocked_reason": str | None,
            "package_info": {
                "name": str,
                "version": str,
                "summary": str,
                "downloads": int | None
            } | None
        }

    Example:
        # Check before installing
        result = dexai_verify_package("pyfiglet")
        if result["safe"]:
            # OK to install
            dexai_install_package("pyfiglet")
        else:
            # Don't install, explain to user
            print(f"Cannot install: {result['warnings']}")
    """
    try:
        from tools.security.package_security import verify_package_security_sync

        # Run the security verification
        result = verify_package_security_sync(package_name)

        return {
            "success": True,
            "tool": "dexai_verify_package",
            "package": package_name,
            "version": version,
            "safe": result.get("safe", False),
            "risk_level": result.get("risk_level", "high"),
            "recommendation": result.get("recommendation", "skip"),
            "warnings": result.get("warnings", []),
            "blocked_reason": result.get("blocked_reason"),
            "package_info": result.get("package_info"),
        }

    except ImportError as e:
        logger.error(f"Package security module not available: {e}")
        return {
            "success": False,
            "tool": "dexai_verify_package",
            "package": package_name,
            "error": f"Security module not available: {e}",
            "safe": False,
            "risk_level": "high",
            "recommendation": "skip",
            "warnings": ["Security verification unavailable - cannot install safely"],
        }
    except Exception as e:
        logger.error(f"Package verification failed: {e}")
        return {
            "success": False,
            "tool": "dexai_verify_package",
            "package": package_name,
            "error": str(e),
            "safe": False,
            "risk_level": "high",
            "recommendation": "skip",
            "warnings": [f"Verification error: {e}"],
        }


# =============================================================================
# Tool: dexai_install_package
# =============================================================================


def dexai_install_package(
    package_name: str,
    version: str | None = None,
) -> dict[str, Any]:
    """
    Install a Python package in the workspace after security verification.

    Uses `uv pip install` for fast, reliable installation.
    Packages are installed in the current Python environment.
    Security verification is always performed before installation.

    Args:
        package_name: Name of the package to install (e.g., "pyfiglet>=2.0")
        version: Optional version constraint (e.g., ">=2.0.0", "==1.0.0")

    Returns:
        {
            "success": bool,
            "tool": "dexai_install_package",
            "package": str,
            "installed_version": str | None,
            "message": str,
            "output": str  # Command output
        }

    Example:
        # First verify, then install
        verify_result = dexai_verify_package("pyfiglet")
        if verify_result["safe"]:
            install_result = dexai_install_package("pyfiglet")
            if install_result["success"]:
                print(f"Installed {install_result['installed_version']}")
    """
    # Build package spec
    package_spec = package_name
    if version:
        if not version.startswith((">=", "<=", "==", "~=", "!=")):
            version = f">={version}"
        package_spec = f"{package_name}{version}"

    # Always verify before installation
    verify_result = dexai_verify_package(package_name, version)
    if not verify_result.get("safe", False):
        return {
            "success": False,
            "tool": "dexai_install_package",
            "package": package_spec,
            "installed_version": None,
            "message": f"Package failed security verification: {verify_result.get('warnings', ['Unknown'])}",
            "output": "",
            "verification_result": verify_result,
        }

    # Log the installation attempt
    try:
        from tools.dashboard.backend.database import log_audit
        log_audit(
            event_type="package.install",
            severity="info",
            actor="agent",
            target=package_spec,
            details={"package": package_name, "version": version},
        )
    except Exception:
        pass

    # Install using uv pip
    try:
        # Try uv first (faster)
        cmd = ["uv", "pip", "install", package_spec]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            # Fall back to pip if uv fails
            cmd = [sys.executable, "-m", "pip", "install", package_spec]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

        if result.returncode == 0:
            # Try to get installed version
            installed_version = _get_installed_version(package_name)

            return {
                "success": True,
                "tool": "dexai_install_package",
                "package": package_spec,
                "installed_version": installed_version,
                "message": f"Successfully installed {package_name}" + (f" {installed_version}" if installed_version else ""),
                "output": result.stdout,
            }
        else:
            return {
                "success": False,
                "tool": "dexai_install_package",
                "package": package_spec,
                "installed_version": None,
                "message": f"Installation failed: {result.stderr or result.stdout}",
                "output": result.stderr or result.stdout,
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "tool": "dexai_install_package",
            "package": package_spec,
            "installed_version": None,
            "message": "Installation timed out (>120s)",
            "output": "",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_install_package",
            "package": package_spec,
            "installed_version": None,
            "message": f"Installation error: {e}",
            "output": "",
        }


def _get_installed_version(package_name: str) -> str | None:
    """Get the installed version of a package."""
    try:
        import importlib.metadata
        return importlib.metadata.version(package_name)
    except Exception:
        return None


# =============================================================================
# Tool Registry
# =============================================================================


DEPENDENCY_TOOLS = {
    "dexai_get_skill_dependency_setting": {
        "function": dexai_get_skill_dependency_setting,
        "description": "Get user's preference for skill dependency installation",
        "parameters": {
            "user_id": {"type": "string", "required": False, "default": "default"},
        },
    },
    "dexai_verify_package": {
        "function": dexai_verify_package,
        "description": "Verify a package is safe to install (security check)",
        "parameters": {
            "package_name": {"type": "string", "required": True},
            "version": {"type": "string", "required": False},
        },
    },
    "dexai_install_package": {
        "function": dexai_install_package,
        "description": "Install a Python package after security verification",
        "parameters": {
            "package_name": {"type": "string", "required": True},
            "version": {"type": "string", "required": False},
        },
    },
}


def get_tool(tool_name: str):
    """Get a tool function by name."""
    tool_info = DEPENDENCY_TOOLS.get(tool_name)
    if tool_info:
        return tool_info["function"]
    return None


def list_tools() -> list[str]:
    """List all available dependency tools."""
    return list(DEPENDENCY_TOOLS.keys())


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing dependency tools."""
    import argparse

    parser = argparse.ArgumentParser(description="DexAI Dependency MCP Tools")
    parser.add_argument("--tool", required=True, help="Tool to invoke")
    parser.add_argument("--args", help="JSON arguments")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        print("Available dependency tools:")
        for name, info in DEPENDENCY_TOOLS.items():
            print(f"  {name}: {info['description']}")
        return

    tool_func = get_tool(args.tool)
    if not tool_func:
        print(f"Unknown tool: {args.tool}")
        print(f"Available: {list_tools()}")
        sys.exit(1)

    # Parse arguments
    tool_args = {}
    if args.args:
        tool_args = json.loads(args.args)

    # Invoke tool
    result = tool_func(**tool_args)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
