"""Access to the Prometheus exposition.

The gateway port is also the browser-facing port, so metrics (usage, cost) are off by default:
set ``RELAY_METRICS_TOKEN`` (scrape with ``Authorization: Bearer <token>``) or, on a private
network, ``RELAY_METRICS_ENABLED=1`` for unauthenticated access.
"""

from __future__ import annotations

import os

from relay_adapter_observability_prometheus import PrometheusMetricsBridge
from relay_gateway.core.errors import Disabled
from relay_gateway.core.security import require_bearer


class MetricsService:
    def __init__(self, bridge: PrometheusMetricsBridge) -> None:
        self._bridge = bridge

    def render(self, authorization: str | None) -> tuple[bytes, str]:
        token = os.environ.get("RELAY_METRICS_TOKEN", "").strip()
        if token:
            require_bearer(authorization, token, detail="invalid metrics token")
        elif os.environ.get("RELAY_METRICS_ENABLED", "").lower() not in ("1", "true", "yes"):
            raise Disabled("metrics are disabled")
        return self._bridge.render()
