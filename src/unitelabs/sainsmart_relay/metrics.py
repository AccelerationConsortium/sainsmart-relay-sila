"""
Prometheus metrics for the relay connector.

Exposes a /metrics endpoint (scraped by the observability stack). Bind on 0.0.0.0
so a containerized Prometheus can reach this native host process via
host.docker.internal. Metrics are no-ops until `start()` is called, so the
connector has zero hard dependency on Prometheus (deploy-without-Prometheus works).
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger(__name__)


class RelayMetrics:
    """Holds the relay metric series and updates them from the feature/io layer."""

    def __init__(self, registry: CollectorRegistry = REGISTRY) -> None:
        self.active_channel = Gauge(
            "relay_active_channel", "Currently active channel index, or -1 if none", registry=registry
        )
        self.channel_state = Gauge(
            "relay_channel_state", "Per-channel coil state (1=closed)", ["channel"], registry=registry
        )
        self.switches_total = Counter(
            "relay_switches_total", "Successful channel activations", ["channel"], registry=registry
        )
        self.command_errors_total = Counter(
            "relay_command_errors_total", "Failed relay operations", ["op", "reason"], registry=registry
        )
        self.command_duration = Histogram(
            "relay_command_duration_seconds", "Relay command latency", ["op"], registry=registry
        )
        self.last_switch_ts = Gauge(
            "relay_last_switch_timestamp_seconds", "Unix time of the last successful switch", registry=registry
        )
        # Info-style metric: SiLA server identity from the CDK (constant value 1, identity in labels).
        self.server_info = Gauge(
            "sila_server_info",
            "SiLA server metadata exposed by the CDK (value is always 1)",
            ["uuid", "name", "type", "version", "vendor_url"],
            registry=registry,
        )
        self.active_channel.set(-1)

    def set_server_info(self, *, uuid: str, name: str, server_type: str, version: str, vendor_url: str) -> None:
        """Publish the SiLA server identity (call once at startup with values from the CDK config)."""
        self.server_info.labels(
            uuid=uuid, name=name, type=server_type, version=str(version), vendor_url=vendor_url
        ).set(1)

    @contextlib.contextmanager
    def time_command(self, op: str) -> Iterator[None]:
        """Time an operation and, on exception, increment the error counter labelled by type."""
        with self.command_duration.labels(op=op).time():
            try:
                yield
            except Exception as exc:
                self.command_errors_total.labels(op=op, reason=type(exc).__name__).inc()
                raise

    def _publish_states(self, states: list[bool]) -> None:
        for i, on in enumerate(states):
            self.channel_state.labels(channel=str(i)).set(1 if on else 0)
        active = [i for i, on in enumerate(states) if on]
        self.active_channel.set(active[0] if len(active) == 1 else -1)

    def on_switch(self, channel: int, states: list[bool]) -> None:
        """Record a successful switch to `channel` and publish the resulting channel states."""
        self.switches_total.labels(channel=str(channel)).inc()
        self.last_switch_ts.set(time.time())
        self._publish_states(states)

    def on_set(self, states: list[bool]) -> None:
        """Publish channel states after a direct set / deactivate-all."""
        self._publish_states(states)


def start_metrics_server(port: int, addr: str = "0.0.0.0") -> None:
    """Start the Prometheus exposition server (bind all interfaces for host.docker.internal)."""
    start_http_server(port, addr=addr)
    logger.info("Prometheus metrics on http://%s:%d/metrics", addr, port)
