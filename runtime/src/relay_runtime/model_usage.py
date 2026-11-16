"""Token usage and cost per model call, published as ``METRIC`` events named ``model.usage``.

Providers yield ``{"type": "usage", "model", "input_tokens", "output_tokens",
"cached_input_tokens"}`` once per completion. ``input_tokens`` includes the cached ones.

Cost needs prices, which Relay does not ship (they change and differ per provider): set
``RELAY_MODEL_PRICES`` to JSON, USD per 1M tokens, keyed by model id with ``"*"`` as fallback
(the numbers below only show the format — use your provider's current price list)::

    {"my-model": {"input": 1.00, "output": 4.00, "cached_input": 0.50}}

``cached_input`` is optional (defaults to the ``input`` price). Without a price for the model,
tokens are still recorded and ``cost_usd`` is omitted.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MODEL_USAGE_METRIC = "model.usage"
_PER_MILLION = 1_000_000


def load_prices() -> dict[str, dict[str, float]]:
    """Parse ``RELAY_MODEL_PRICES``; a malformed value is ignored with a warning."""
    raw = os.environ.get("RELAY_MODEL_PRICES", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("RELAY_MODEL_PRICES is not valid JSON; model cost will not be reported")
        return {}
    prices: dict[str, dict[str, float]] = {}
    for model, entry in parsed.items() if isinstance(parsed, dict) else []:
        if not isinstance(entry, dict):
            continue
        try:
            prices[str(model)] = {key: float(value) for key, value in entry.items()}
        except (TypeError, ValueError):
            logger.warning("RELAY_MODEL_PRICES entry for %s is not numeric; ignored", model)
    return prices


def _count(chunk: dict[str, Any], key: str) -> int:
    value = chunk.get(key)
    return int(value) if isinstance(value, (int, float)) and value > 0 else 0


def usage_details(chunk: dict[str, Any], prices: dict[str, dict[str, float]]) -> dict[str, Any]:
    """``details`` for a ``model.usage`` metric from a provider usage chunk."""
    model = str(chunk.get("model") or "unknown")
    input_tokens = _count(chunk, "input_tokens")
    output_tokens = _count(chunk, "output_tokens")
    cached = min(_count(chunk, "cached_input_tokens"), input_tokens)
    details: dict[str, Any] = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached,
        "total_tokens": input_tokens + output_tokens,
    }
    price = prices.get(model) or prices.get("*")
    if price and "input" in price and "output" in price:
        cost = (
            (input_tokens - cached) * price["input"]
            + cached * price.get("cached_input", price["input"])
            + output_tokens * price["output"]
        ) / _PER_MILLION
        details["cost_usd"] = round(cost, 6)
    return details


def summarize_usage(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals over ``model.usage`` metric rows (``{"name", "details"}``), for a session timeline."""
    totals: dict[str, Any] = {
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "total_tokens": 0,
    }
    cost = 0.0
    priced = False
    for row in metrics:
        details = row.get("details")
        if row.get("name") != MODEL_USAGE_METRIC or not isinstance(details, dict):
            continue
        totals["model_calls"] += 1
        for key in ("input_tokens", "output_tokens", "cached_input_tokens", "total_tokens"):
            totals[key] += _count(details, key)
        if isinstance(details.get("cost_usd"), (int, float)):
            cost += float(details["cost_usd"])
            priced = True
    if priced:
        totals["cost_usd"] = round(cost, 6)
    return totals
