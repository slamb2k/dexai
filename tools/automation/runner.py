"""
Tool: Background Runner (Daemon)
Purpose: Orchestrate all automation components

Features:
- Runs scheduler, heartbeat, notification, and trigger loops
- PID file for single-instance enforcement
- Status file for health checks
- Graceful shutdown handling
- Daemonization support

Usage:
    python tools/automation/runner.py --start
    python tools/automation/runner.py --start --daemon
    python tools/automation/runner.py --stop
    python tools/automation/runner.py --status
    python tools/automation/runner.py --health

Dependencies:
    - asyncio (stdlib)
    - pyyaml
"""

import argparse
import asyncio
import atexit
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.automation import CONFIG_PATH


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    default_config = {
        "heartbeat": {"enabled": True, "interval_minutes": 30},
        "cron": {"enabled": True, "poll_interval_seconds": 60, "max_concurrent_jobs": 3},
        "triggers": {"enabled": True, "file_watcher": {"enabled": True}},
        "notifications": {"enabled": True, "process_interval": 10},
        "runner": {
            "pid_file": ".tmp/automation.pid",
            "status_file": ".tmp/automation_status.json",
            "shutdown_timeout": 30,
            "log_file": ".tmp/automation.log",
        },
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml

        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        return config if config else default_config
    except Exception:
        return default_config


class AutomationRunner:
    """Main automation daemon that orchestrates all components."""

    def __init__(self):
        self.config = load_config()
        self.running = False
        self.tasks: list[asyncio.Task] = []
        self.start_time: datetime | None = None

        # Get paths from config
        runner_config = self.config.get("runner", {})
        self.pid_file = PROJECT_ROOT / runner_config.get("pid_file", ".tmp/automation.pid")
        self.status_file = PROJECT_ROOT / runner_config.get(
            "status_file", ".tmp/automation_status.json"
        )
        self.shutdown_timeout = runner_config.get("shutdown_timeout", 30)

        # Component status
        self.component_status = {
            "scheduler": {"running": False, "last_run": None, "errors": 0},
            "heartbeat": {"running": False, "last_run": None, "errors": 0},
            "notifications": {"running": False, "last_run": None, "errors": 0},
            "file_watcher": {"running": False, "last_run": None, "errors": 0},
        }

    def _ensure_dirs(self):
        """Ensure required directories exist."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)

    def _write_pid(self):
        """Write PID file."""
        self._ensure_dirs()
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self):
        """Remove PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()

    def _read_pid(self) -> int | None:
        """Read PID from file."""
        if not self.pid_file.exists():
            return None
        try:
            with open(self.pid_file) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _is_running(self) -> bool:
        """Check if another instance is running."""
        pid = self._read_pid()
        if pid is None:
            return False

        # Check if process exists
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            # Process doesn't exist, remove stale PID file
            self._remove_pid()
            return False

    def _write_status(self):
        """Write status file."""
        status = {
            "running": self.running,
            "pid": os.getpid() if self.running else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds()
            if self.start_time
            else 0,
            "components": self.component_status,
            "updated_at": datetime.now().isoformat(),
        }

        self._ensure_dirs()
        with open(self.status_file, "w") as f:
            json.dump(status, f, indent=2)

    def _read_status(self) -> dict[str, Any]:
        """Read status file."""
        if not self.status_file.exists():
            return {"running": False}
        try:
            with open(self.status_file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"running": False}

    async def _run_scheduler_loop(self):
        """Run the cron scheduler loop."""
        from tools.automation import scheduler

        cron_config = self.config.get("cron", {})
        poll_interval = cron_config.get("poll_interval_seconds", 60)
        max_concurrent = cron_config.get("max_concurrent_jobs", 3)

        self.component_status["scheduler"]["running"] = True

        while self.running:
            try:
                # Get due jobs
                due_jobs = scheduler.get_due_jobs()

                # Execute up to max_concurrent jobs
                for job in due_jobs[:max_concurrent]:
                    try:
                        result = scheduler.run_job(job["id"], triggered_by="schedule")

                        # Mark job as run (updates next_run)
                        scheduler.mark_job_run(job["id"])

                        # Log success
                        self._log(f"Scheduler: Executed job '{job['name']}'")

                    except Exception as e:
                        self._log(f"Scheduler: Error executing job '{job['name']}': {e}")
                        self.component_status["scheduler"]["errors"] += 1

                self.component_status["scheduler"]["last_run"] = datetime.now().isoformat()
                self._write_status()

            except Exception as e:
                self._log(f"Scheduler loop error: {e}")
                self.component_status["scheduler"]["errors"] += 1

            await asyncio.sleep(poll_interval)

        self.component_status["scheduler"]["running"] = False

    async def _run_heartbeat_loop(self):
        """Run the heartbeat check loop."""
        from tools.automation import heartbeat

        hb_config = self.config.get("heartbeat", {})
        interval_minutes = hb_config.get("interval_minutes", 30)

        self.component_status["heartbeat"]["running"] = True

        while self.running:
            try:
                result = heartbeat.run_heartbeat()

                if result.get("skipped"):
                    self._log(f"Heartbeat: Skipped - {result.get('reason')}")
                else:
                    self._log(f"Heartbeat: Running {result.get('check_count', 0)} checks")
                    # The actual LLM execution would happen here
                    # For now, we just prepare the prompt

                self.component_status["heartbeat"]["last_run"] = datetime.now().isoformat()
                self._write_status()

            except Exception as e:
                self._log(f"Heartbeat loop error: {e}")
                self.component_status["heartbeat"]["errors"] += 1

            await asyncio.sleep(interval_minutes * 60)

        self.component_status["heartbeat"]["running"] = False

    async def _run_notification_loop(self):
        """Run the notification processing loop."""
        from tools.automation import notify

        notif_config = self.config.get("notifications", {})
        process_interval = notif_config.get("process_interval", 10)

        self.component_status["notifications"]["running"] = True

        while self.running:
            try:
                result = await notify.process_pending()

                if result.get("processed", 0) > 0:
                    self._log(
                        f"Notifications: Processed {result['processed']} "
                        f"(sent: {result.get('sent', 0)}, failed: {result.get('failed', 0)})"
                    )

                self.component_status["notifications"]["last_run"] = datetime.now().isoformat()
                self._write_status()

            except Exception as e:
                self._log(f"Notification loop error: {e}")
                self.component_status["notifications"]["errors"] += 1

            await asyncio.sleep(process_interval)

        self.component_status["notifications"]["running"] = False

    async def _run_file_watcher(self):
        """Run the file watcher for triggers."""
        from tools.automation import triggers

        if not triggers.WATCHDOG_AVAILABLE:
            self._log("File watcher: watchdog not available")
            return

        trigger_config = self.config.get("triggers", {})
        if not trigger_config.get("file_watcher", {}).get("enabled", True):
            self._log("File watcher: disabled in config")
            return

        self.component_status["file_watcher"]["running"] = True

        # Set up callback that queues trigger fires
        trigger_queue: asyncio.Queue = asyncio.Queue()

        def on_trigger(trigger_id: str, context: dict):
            try:
                trigger_queue.put_nowait((trigger_id, context))
            except asyncio.QueueFull:
                pass

        observer = triggers.setup_file_watcher(callback=on_trigger)
        if not observer:
            self._log("File watcher: failed to start")
            self.component_status["file_watcher"]["running"] = False
            return

        observer.start()
        self._log("File watcher: started")

        try:
            while self.running:
                try:
                    # Process trigger queue with timeout
                    trigger_id, context = await asyncio.wait_for(trigger_queue.get(), timeout=1.0)

                    result = await triggers.fire_trigger(trigger_id, context)
                    if not result.get("debounced"):
                        self._log(f"File watcher: Fired trigger for {context.get('path')}")

                    self.component_status["file_watcher"]["last_run"] = datetime.now().isoformat()

                except TimeoutError:
                    pass
                except Exception as e:
                    self._log(f"File watcher error: {e}")
                    self.component_status["file_watcher"]["errors"] += 1

        finally:
            observer.stop()
            observer.join()
            self.component_status["file_watcher"]["running"] = False

    def _log(self, message: str):
        """Log a message (to stdout and optionally to file)."""
        timestamp = datetime.now().isoformat()
        log_line = f"[{timestamp}] {message}"
        print(log_line)

        # Also write to log file if configured
        runner_config = self.config.get("runner", {})
        log_file = runner_config.get("log_file")
        if log_file:
            log_path = PROJECT_ROOT / log_file
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(log_line + "\n")

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            self._log(f"Received signal {signum}, shutting down...")
            self.running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    async def start(self):
        """Start the automation daemon."""
        if self._is_running():
            print(f"Error: Automation daemon already running (PID: {self._read_pid()})")
            return False

        self.running = True
        self.start_time = datetime.now()

        # Write PID file
        self._write_pid()
        atexit.register(self._remove_pid)

        # Set up signal handlers
        self._setup_signal_handlers()

        self._log("Automation daemon starting...")
        self._write_status()

        # Start component loops
        cron_config = self.config.get("cron", {})
        hb_config = self.config.get("heartbeat", {})
        notif_config = self.config.get("notifications", {})
        trigger_config = self.config.get("triggers", {})

        if cron_config.get("enabled", True):
            self.tasks.append(asyncio.create_task(self._run_scheduler_loop()))
            self._log("Started: Scheduler loop")

        if hb_config.get("enabled", True):
            self.tasks.append(asyncio.create_task(self._run_heartbeat_loop()))
            self._log("Started: Heartbeat loop")

        if notif_config.get("enabled", True):
            self.tasks.append(asyncio.create_task(self._run_notification_loop()))
            self._log("Started: Notification loop")

        if trigger_config.get("enabled", True) and trigger_config.get("file_watcher", {}).get(
            "enabled", True
        ):
            self.tasks.append(asyncio.create_task(self._run_file_watcher()))
            self._log("Started: File watcher")

        self._log(f"Automation daemon started with {len(self.tasks)} components")

        # Wait for all tasks
        try:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        except Exception as e:
            self._log(f"Error in main loop: {e}")

        # Cleanup
        self.running = False
        self._write_status()
        self._remove_pid()
        self._log("Automation daemon stopped")

        return True

    def stop(self) -> dict[str, Any]:
        """Stop the running daemon."""
        pid = self._read_pid()
        if pid is None:
            return {"success": False, "error": "Daemon not running"}

        try:
            os.kill(pid, signal.SIGTERM)
            return {"success": True, "pid": pid, "message": f"Sent SIGTERM to PID {pid}"}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def get_status(self) -> dict[str, Any]:
        """Get daemon status."""
        status = self._read_status()
        pid = self._read_pid()

        # Check if actually running
        if pid:
            try:
                os.kill(pid, 0)
                status["actually_running"] = True
            except OSError:
                status["actually_running"] = False
        else:
            status["actually_running"] = False

        status["pid_file"] = str(self.pid_file)
        status["status_file"] = str(self.status_file)

        return status

    def health_check(self) -> dict[str, Any]:
        """Perform health check."""
        status = self.get_status()

        health = {"healthy": status.get("actually_running", False), "components": {}}

        if status.get("components"):
            for name, comp_status in status["components"].items():
                health["components"][name] = {
                    "running": comp_status.get("running", False),
                    "errors": comp_status.get("errors", 0),
                    "healthy": comp_status.get("running", False)
                    and comp_status.get("errors", 0) < 10,
                }

        # Check if any component has too many errors
        total_errors = sum(
            comp.get("errors", 0) for comp in (status.get("components") or {}).values()
        )

        health["total_errors"] = total_errors
        health["healthy"] = health["healthy"] and total_errors < 50

        return health


def daemonize():
    """Fork and daemonize the process."""
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        print(f"Fork #1 failed: {e}")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir(str(PROJECT_ROOT))
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        print(f"Fork #2 failed: {e}")
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    # Get log file path
    config = load_config()
    log_file = config.get("runner", {}).get("log_file", ".tmp/automation.log")
    log_path = PROJECT_ROOT / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open("/dev/null") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())

    with open(log_path, "a") as log:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())


def main():
    parser = argparse.ArgumentParser(description="Automation Runner")
    parser.add_argument("--start", action="store_true", help="Start the daemon")
    parser.add_argument("--stop", action="store_true", help="Stop the daemon")
    parser.add_argument("--status", action="store_true", help="Show daemon status")
    parser.add_argument("--health", action="store_true", help="Health check")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (background)")
    parser.add_argument("--foreground", action="store_true", help="Run in foreground (default)")

    args = parser.parse_args()
    runner = AutomationRunner()
    result = None

    if args.start:
        if args.daemon and hasattr(os, "fork"):
            print("Starting automation daemon in background...")
            daemonize()

        # Run the daemon
        success = asyncio.run(runner.start())
        result = {"success": success}

    elif args.stop:
        result = runner.stop()

    elif args.status:
        result = {"success": True, "status": runner.get_status()}

    elif args.health:
        result = {"success": True, "health": runner.health_check()}

    else:
        parser.print_help()
        sys.exit(0)

    if result:
        if result.get("success"):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
