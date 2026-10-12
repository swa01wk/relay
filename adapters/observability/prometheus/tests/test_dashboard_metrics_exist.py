"""The shipped Grafana dashboard and alert rules must only reference metrics the bridge exports."""

from __future__ import annotations

import json
import re
from pathlib import Path

from relay_adapter_observability_prometheus import PrometheusMetricsBridge

OBSERVABILITY = Path(__file__).resolve().parents[4] / "infra" / "observability"


def _exported() -> set[str]:
    bridge = PrometheusMetricsBridge(active_sessions=lambda: 0)
    names: set[str] = set()
    for family in bridge.registry.collect():
        suffixes = {"counter": ["_total"], "histogram": ["_bucket", "_sum", "_count"]}.get(family.type, [""])
        names.update(family.name + suffix for suffix in suffixes)
        names.add(family.name)  # alert descriptions name the metric family
    return names


def _referenced(text: str) -> set[str]:
    return set(re.findall(r"\brelay_[a-z_]+", text))


def test_dashboard_and_alerts_use_exported_metrics():
    exported = _exported()
    dashboard = json.loads((OBSERVABILITY / "grafana" / "dashboards" / "relay-overview.json").read_text())
    expressions = " ".join(t["expr"] for p in dashboard["panels"] for t in p.get("targets", []))
    alerts = (OBSERVABILITY / "alerts.yml").read_text()

    assert _referenced(expressions) and _referenced(alerts)
    assert _referenced(expressions) - exported == set()
    assert _referenced(alerts) - exported == set()
