"""Container-based execution for agent sessions.

Provides OS-level isolation by running commands in ephemeral Docker containers.
Opt-in via DEXAI_CONTAINER_ISOLATION=true environment variable.

Each session gets a dedicated, resource-limited container with a mounted
workspace directory.  Network access is disabled by default.

Usage:
    from tools.security.container_executor import get_executor

    executor = get_executor(session_id, workspace_dir)
    if executor:
        executor.start()
        result = executor.execute("python myscript.py")
        executor.stop()
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONTAINER_ISOLATION_ENABLED = (
    os.getenv("DEXAI_CONTAINER_ISOLATION", "false").lower() == "true"
)

# Container defaults
_IMAGE = os.getenv("DEXAI_CONTAINER_IMAGE", "python:3.12-slim")
_MEM_LIMIT = os.getenv("DEXAI_CONTAINER_MEM_LIMIT", "512m")
_CPU_QUOTA = int(os.getenv("DEXAI_CONTAINER_CPU_QUOTA", "50000"))  # 50% of one core
_NETWORK_DISABLED = os.getenv("DEXAI_CONTAINER_NETWORK", "false").lower() != "true"


class ContainerExecutor:
    """Execute commands inside an ephemeral Docker container.

    The container is created on ``start()`` and destroyed on ``stop()``.
    Between those calls, ``execute()`` runs commands inside the container.

    Args:
        session_id: Unique session identifier (used for container naming).
        workspace_dir: Host directory mounted as /workspace inside the container.
    """

    def __init__(self, session_id: str, workspace_dir: str | Path) -> None:
        self.session_id = session_id
        self.workspace_dir = Path(workspace_dir)
        self.container_name = f"dexai-session-{session_id[:12]}"
        self._container: Any = None  # docker.models.containers.Container
        self._client: Any = None     # docker.DockerClient

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> dict[str, Any]:
        """Start an ephemeral container for this session.

        Returns:
            dict with ``success``, ``container_name``, and optional ``error``.
        """
        try:
            import docker
        except ImportError:
            return {
                "success": False,
                "error": "docker-py not installed. Run: uv pip install docker",
            }

        try:
            self._client = docker.from_env()

            # Remove any stale container with the same name
            try:
                stale = self._client.containers.get(self.container_name)
                stale.remove(force=True)
                logger.info("Removed stale container %s", self.container_name)
            except docker.errors.NotFound:
                pass

            self._container = self._client.containers.run(
                image=_IMAGE,
                name=self.container_name,
                command="sleep infinity",
                detach=True,
                mem_limit=_MEM_LIMIT,
                cpu_quota=_CPU_QUOTA,
                network_disabled=_NETWORK_DISABLED,
                volumes={
                    str(self.workspace_dir.resolve()): {
                        "bind": "/workspace",
                        "mode": "rw",
                    }
                },
                working_dir="/workspace",
                # Drop all capabilities except minimal set
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
            )
            logger.info(
                "Started container %s (image=%s)", self.container_name, _IMAGE
            )
            return {
                "success": True,
                "container_name": self.container_name,
            }

        except Exception as exc:
            logger.error("Failed to start container: %s", exc)
            return {"success": False, "error": str(exc)}

    def stop(self) -> dict[str, Any]:
        """Stop and remove the session container.

        Returns:
            dict with ``success`` and optional ``error``.
        """
        if self._container is None:
            return {"success": True, "message": "No container to stop"}

        try:
            self._container.remove(force=True)
            logger.info("Stopped and removed container %s", self.container_name)
            self._container = None
            return {"success": True}
        except Exception as exc:
            logger.error("Failed to stop container %s: %s", self.container_name, exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, command: str, timeout: int = 120) -> dict[str, Any]:
        """Execute a command inside the session container.

        Args:
            command: Shell command string to execute.
            timeout: Maximum seconds before the command is killed.

        Returns:
            dict with ``success``, ``stdout``, ``stderr``, and ``exit_code``.
        """
        if self._container is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Container not started",
                "exit_code": -1,
            }

        try:
            exec_result = self._container.exec_run(
                cmd=["timeout", str(timeout), "bash", "-c", command],
                workdir="/workspace",
                demux=True,
            )
            exit_code = exec_result.exit_code
            stdout_bytes, stderr_bytes = exec_result.output or (b"", b"")

            stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
            stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")

            if exit_code == 124:
                return {
                    "success": False,
                    "stdout": stdout,
                    "stderr": f"Command timed out after {timeout} seconds",
                    "exit_code": 124,
                }

            return {
                "success": exit_code == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
            }

        except Exception as exc:
            logger.error("Container exec failed: %s", exc)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
            }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        """Check whether the session container is running."""
        if self._container is None:
            return False
        try:
            self._container.reload()
            return self._container.status == "running"
        except Exception:
            return False


# ======================================================================
# Module-level helper
# ======================================================================


def get_executor(
    session_id: str, workspace_dir: str | Path
) -> ContainerExecutor | None:
    """Get a container executor if isolation is enabled, else None.

    Args:
        session_id: Unique session identifier.
        workspace_dir: Host directory to mount inside the container.

    Returns:
        ContainerExecutor instance, or None when isolation is disabled.
    """
    if not CONTAINER_ISOLATION_ENABLED:
        return None
    return ContainerExecutor(session_id, workspace_dir)
