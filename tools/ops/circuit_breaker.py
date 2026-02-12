"""
Circuit Breaker for External API Calls

Tracks failure rates per service/provider and temporarily disables
failing services to prevent cascading failures.

States:
    closed  - Normal operation, requests pass through
    open    - Service blocked, failures exceeded threshold
    half_open - Allowing one test request after recovery timeout

Usage:
    from tools.ops.circuit_breaker import circuit_breaker

    if circuit_breaker.can_execute("openrouter"):
        try:
            result = call_openrouter(...)
            circuit_breaker.record_success("openrouter")
        except Exception:
            circuit_breaker.record_failure("openrouter")
    else:
        # Try fallback provider
        ...

Dependencies:
    - threading (stdlib)
    - time (stdlib)
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    """Internal state for a single service circuit."""

    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    state: str = "closed"  # "closed" | "open" | "half_open"
    half_open_attempts: int = 0


class CircuitBreaker:
    """Thread-safe circuit breaker for external service calls.

    Tracks failure rates per service and temporarily disables failing
    services to prevent cascading failures and wasted retries.

    Args:
        failure_threshold: Number of consecutive failures before opening circuit.
        recovery_timeout: Seconds to wait before transitioning from open to half_open.
        half_open_max: Maximum concurrent test requests in half_open state.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self._circuits: dict[str, CircuitState] = {}
        self._lock = threading.Lock()

    def _get_circuit(self, service: str) -> CircuitState:
        """Get or create circuit state for a service. Must hold _lock."""
        if service not in self._circuits:
            self._circuits[service] = CircuitState()
        return self._circuits[service]

    def can_execute(self, service: str) -> bool:
        """Check whether a request to the given service is allowed.

        Args:
            service: Service/provider identifier (e.g. "openrouter", "anthropic").

        Returns:
            True if the request should proceed, False if the circuit is open.
        """
        with self._lock:
            circuit = self._get_circuit(service)

            if circuit.state == "closed":
                return True

            if circuit.state == "open":
                # Check if recovery timeout has elapsed
                elapsed = time.monotonic() - circuit.last_failure_time
                if elapsed >= self.recovery_timeout:
                    circuit.state = "half_open"
                    circuit.half_open_attempts = 0
                    logger.info(
                        f"Circuit breaker for '{service}' transitioning to half_open "
                        f"after {elapsed:.1f}s"
                    )
                    return True
                return False

            if circuit.state == "half_open":
                # Allow limited test requests
                if circuit.half_open_attempts < self.half_open_max:
                    circuit.half_open_attempts += 1
                    return True
                return False

            return True  # Defensive default

    def record_success(self, service: str) -> None:
        """Record a successful request for the given service.

        If the circuit is half_open, transitions back to closed.

        Args:
            service: Service/provider identifier.
        """
        with self._lock:
            circuit = self._get_circuit(service)
            circuit.success_count += 1
            circuit.last_success_time = time.monotonic()

            if circuit.state == "half_open":
                # Test request succeeded, close the circuit
                circuit.state = "closed"
                circuit.failure_count = 0
                circuit.half_open_attempts = 0
                logger.info(f"Circuit breaker for '{service}' closed (recovered)")

            elif circuit.state == "closed":
                # Reset failure count on success
                circuit.failure_count = 0

    def record_failure(self, service: str) -> None:
        """Record a failed request for the given service.

        If failures exceed the threshold, opens the circuit.

        Args:
            service: Service/provider identifier.
        """
        with self._lock:
            circuit = self._get_circuit(service)
            circuit.failure_count += 1
            circuit.last_failure_time = time.monotonic()

            if circuit.state == "half_open":
                # Test request failed, back to open
                circuit.state = "open"
                circuit.half_open_attempts = 0
                logger.warning(
                    f"Circuit breaker for '{service}' re-opened (half_open test failed)"
                )

            elif circuit.state == "closed":
                if circuit.failure_count >= self.failure_threshold:
                    circuit.state = "open"
                    logger.warning(
                        f"Circuit breaker for '{service}' OPENED "
                        f"({circuit.failure_count} consecutive failures)"
                    )

    def get_state(self, service: str) -> str:
        """Get the current circuit state for a service.

        Args:
            service: Service/provider identifier.

        Returns:
            Circuit state: "closed", "open", or "half_open".
        """
        with self._lock:
            circuit = self._get_circuit(service)

            # Check for timeout transition without modifying state
            if circuit.state == "open":
                elapsed = time.monotonic() - circuit.last_failure_time
                if elapsed >= self.recovery_timeout:
                    return "half_open"

            return circuit.state

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Get states for all tracked services.

        Returns:
            Dict mapping service name to state info dict.
        """
        with self._lock:
            result = {}
            for service, circuit in self._circuits.items():
                effective_state = circuit.state
                if circuit.state == "open":
                    elapsed = time.monotonic() - circuit.last_failure_time
                    if elapsed >= self.recovery_timeout:
                        effective_state = "half_open"

                result[service] = {
                    "state": effective_state,
                    "failure_count": circuit.failure_count,
                    "success_count": circuit.success_count,
                    "last_failure_time": circuit.last_failure_time,
                    "last_success_time": circuit.last_success_time,
                }
            return result

    def reset(self, service: str | None = None) -> None:
        """Reset circuit state for a service or all services.

        Args:
            service: Service to reset, or None to reset all.
        """
        with self._lock:
            if service is None:
                self._circuits.clear()
                logger.info("All circuit breakers reset")
            elif service in self._circuits:
                self._circuits[service] = CircuitState()
                logger.info(f"Circuit breaker for '{service}' reset")


# Module-level singleton
circuit_breaker = CircuitBreaker()
