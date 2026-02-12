"""
Prometheus-Compatible Metrics Collector

Hand-rolled OpenMetrics text format output for Prometheus scraping.
No external dependency on prometheus_client.

Usage:
    from tools.ops.prometheus import metrics

    metrics.inc_counter("dexai_requests_total", labels={"channel": "telegram"})
    metrics.set_gauge("dexai_active_sessions", 5.0)
    metrics.observe_histogram("dexai_request_duration_seconds", 0.123)

    # Get Prometheus-format text
    output = metrics.format_openmetrics()

Dependencies:
    - threading (stdlib)
    - time (stdlib)
    - math (stdlib)
"""

import logging
import math
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Default histogram buckets (seconds)
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _labels_key(labels: dict[str, str] | None) -> str:
    """Convert labels dict to a sorted, deterministic string key."""
    if not labels:
        return ""
    return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))


def _labels_suffix(labels: dict[str, str] | None) -> str:
    """Format labels for Prometheus text output."""
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


class MetricsCollector:
    """Thread-safe Prometheus-compatible metrics collector.

    Supports counters, gauges, and histograms. Outputs OpenMetrics
    text format suitable for Prometheus scraping at /metrics.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key = (name, labels_key) -> value
        self._counters: dict[tuple[str, str], float] = {}
        self._gauges: dict[tuple[str, str], float] = {}
        # Histogram bucket counters: key -> {bucket_le: count}
        self._histogram_buckets: dict[tuple[str, str], dict[float, int]] = {}
        self._histogram_sums: dict[tuple[str, str], float] = {}
        self._histogram_counts: dict[tuple[str, str], int] = {}
        # Track label dicts for formatting
        self._counter_labels: dict[tuple[str, str], dict[str, str] | None] = {}
        self._gauge_labels: dict[tuple[str, str], dict[str, str] | None] = {}
        self._histogram_labels: dict[tuple[str, str], dict[str, str] | None] = {}
        # Track metric help/type metadata
        self._metric_help: dict[str, str] = {}
        self._metric_types: dict[str, str] = {}

    def set_help(self, name: str, help_text: str) -> None:
        """Set HELP text for a metric.

        Args:
            name: Metric name.
            help_text: Description of the metric.
        """
        self._metric_help[name] = help_text

    def inc_counter(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        value: float = 1.0,
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Counter metric name (should end with _total by convention).
            labels: Optional label key-value pairs.
            value: Value to increment by (must be positive).
        """
        if value < 0:
            logger.warning(f"Counter '{name}' cannot be decremented (value={value})")
            return

        key = (name, _labels_key(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value
            self._counter_labels[key] = labels
            if name not in self._metric_types:
                self._metric_types[name] = "counter"

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge metric to a specific value.

        Args:
            name: Gauge metric name.
            value: Current value.
            labels: Optional label key-value pairs.
        """
        key = (name, _labels_key(labels))
        with self._lock:
            self._gauges[key] = value
            self._gauge_labels[key] = labels
            if name not in self._metric_types:
                self._metric_types[name] = "gauge"

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record an observation for a histogram metric.

        Args:
            name: Histogram metric name.
            value: Observed value (e.g. request duration in seconds).
            labels: Optional label key-value pairs.
        """
        key = (name, _labels_key(labels))
        with self._lock:
            if key not in self._histogram_buckets:
                self._histogram_buckets[key] = {b: 0 for b in DEFAULT_BUCKETS}
                self._histogram_buckets[key][float("inf")] = 0
                self._histogram_sums[key] = 0.0
                self._histogram_counts[key] = 0
            for le in DEFAULT_BUCKETS:
                if value <= le:
                    self._histogram_buckets[key][le] += 1
            self._histogram_buckets[key][float("inf")] += 1
            self._histogram_sums[key] += value
            self._histogram_counts[key] += 1
            self._histogram_labels[key] = labels
            if name not in self._metric_types:
                self._metric_types[name] = "histogram"

    def format_openmetrics(self) -> str:
        """Format all metrics in Prometheus text exposition format.

        Returns:
            String in text/plain Prometheus format.
        """
        lines: list[str] = []

        with self._lock:
            # Counters
            emitted_counter_names: set[str] = set()
            for (name, lk), value in sorted(self._counters.items()):
                if name not in emitted_counter_names:
                    if name in self._metric_help:
                        lines.append(f"# HELP {name} {self._metric_help[name]}")
                    lines.append(f"# TYPE {name} counter")
                    emitted_counter_names.add(name)
                labels = self._counter_labels.get((name, lk))
                lines.append(f"{name}{_labels_suffix(labels)} {self._format_value(value)}")

            # Gauges
            emitted_gauge_names: set[str] = set()
            for (name, lk), value in sorted(self._gauges.items()):
                if name not in emitted_gauge_names:
                    if name in self._metric_help:
                        lines.append(f"# HELP {name} {self._metric_help[name]}")
                    lines.append(f"# TYPE {name} gauge")
                    emitted_gauge_names.add(name)
                labels = self._gauge_labels.get((name, lk))
                lines.append(f"{name}{_labels_suffix(labels)} {self._format_value(value)}")

            # Histograms
            emitted_hist_names: set[str] = set()
            for (name, lk), buckets in sorted(self._histogram_buckets.items()):
                if name not in emitted_hist_names:
                    if name in self._metric_help:
                        lines.append(f"# HELP {name} {self._metric_help[name]}")
                    lines.append(f"# TYPE {name} histogram")
                    emitted_hist_names.add(name)

                labels = self._histogram_labels.get((name, lk))
                base_labels = dict(labels) if labels else {}

                for bucket_bound in DEFAULT_BUCKETS:
                    bucket_labels = dict(base_labels)
                    bucket_labels["le"] = str(bucket_bound)
                    lines.append(
                        f"{name}_bucket{_labels_suffix(bucket_labels)} {buckets.get(bucket_bound, 0)}"
                    )

                # +Inf bucket
                inf_labels = dict(base_labels)
                inf_labels["le"] = "+Inf"
                lines.append(
                    f"{name}_bucket{_labels_suffix(inf_labels)} {buckets.get(float('inf'), 0)}"
                )

                # Sum and count
                obs_sum = self._histogram_sums.get((name, lk), 0.0)
                total = self._histogram_counts.get((name, lk), 0)
                lines.append(
                    f"{name}_sum{_labels_suffix(labels)} {self._format_value(obs_sum)}"
                )
                lines.append(
                    f"{name}_count{_labels_suffix(labels)} {total}"
                )

        # Trailing newline
        if lines:
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_value(value: float) -> str:
        """Format a numeric value for Prometheus output."""
        if math.isinf(value):
            return "+Inf" if value > 0 else "-Inf"
        if math.isnan(value):
            return "NaN"
        # Use integer format when possible
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.6g}"

    def collect_system_metrics(self) -> None:
        """Collect current system metrics from various subsystems.

        Gathers metrics from circuit breakers, hook performance,
        and other observable subsystems. Call before format_openmetrics()
        for up-to-date values.
        """
        # Circuit breaker states
        try:
            from tools.ops.circuit_breaker import circuit_breaker

            states = circuit_breaker.get_all_states()
            state_values = {"closed": 0, "half_open": 1, "open": 2}
            for service, info in states.items():
                self.set_gauge(
                    "dexai_circuit_breaker_state",
                    float(state_values.get(info["state"], -1)),
                    labels={"service": service},
                )
                self.set_gauge(
                    "dexai_circuit_breaker_failures",
                    float(info["failure_count"]),
                    labels={"service": service},
                )
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Failed to collect circuit breaker metrics: {e}")

        # Hook performance
        try:
            from tools.agent.hooks import get_hook_performance_summary

            summary = get_hook_performance_summary()
            self.set_gauge(
                "dexai_hook_calls_total",
                float(summary.get("total_calls", 0)),
            )
            for hook_name, stats in summary.get("hooks", {}).items():
                self.set_gauge(
                    "dexai_hook_avg_duration_ms",
                    stats.get("avg_ms", 0.0),
                    labels={"hook": hook_name},
                )
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Failed to collect hook metrics: {e}")


# Module-level singleton
metrics = MetricsCollector()

# Set up default help text
metrics.set_help("dexai_requests_total", "Total number of requests processed")
metrics.set_help("dexai_request_errors_total", "Total number of request errors")
metrics.set_help("dexai_active_sessions", "Number of currently active sessions")
metrics.set_help("dexai_request_duration_seconds", "Request duration in seconds")
metrics.set_help("dexai_circuit_breaker_state", "Circuit breaker state (0=closed, 1=half_open, 2=open)")
metrics.set_help("dexai_circuit_breaker_failures", "Circuit breaker failure count per service")
metrics.set_help("dexai_hook_calls_total", "Total hook invocations")
metrics.set_help("dexai_hook_avg_duration_ms", "Average hook execution time in milliseconds")
