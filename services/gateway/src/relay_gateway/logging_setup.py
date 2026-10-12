"""Gateway logging: one handler for Relay and uvicorn, secrets redacted, optional JSON lines.

``RELAY_LOG_FORMAT=json`` writes one JSON object per line (for Loki, Elasticsearch, CloudWatch…)
with ``session_id`` / ``turn_id`` / ``agent_id`` as fields so a session can be followed across
logs, metrics and traces. Session tokens travel in URLs (``?token=``), so every record is
redacted before it is formatted — including uvicorn's access log.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

REDACTED = "[redacted]"
_SECRET_PARAM = re.compile(r"(?i)\b([a-z_]*token|api[_-]?key|secret|password)=([^&\s\"']+)")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+/=-]+")
# ``key=value`` pairs already present in Relay's log messages become JSON fields.
_FIELD = re.compile(r"\b(session_id|turn_id|agent_id|agent|tool|tool_call_id|approval_id|action_id)=([^\s,;)]+)")
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def redact(text: str) -> str:
    """Hide credentials that appear in URLs and headers."""
    return _BEARER.sub(rf"\1 {REDACTED}", _SECRET_PARAM.sub(rf"\1={REDACTED}", text))


class RedactingFilter(logging.Filter):
    """Redacts the message and its string arguments (kept as arguments, so any formatter works)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(arg) if isinstance(arg, str) else arg for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


class TextFormatter(logging.Formatter):
    def formatException(self, ei: Any) -> str:  # noqa: N802 (logging API name)
        return redact(super().formatException(ei))


class JsonFormatter(logging.Formatter):
    def __init__(self, agent_for_session: Callable[[str], str | None] | None = None) -> None:
        super().__init__()
        self._agent_for_session = agent_for_session

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": message,
        }
        for key, value in _FIELD.findall(message):
            entry.setdefault("agent_id" if key == "agent" else key, value)
        for key, value in record.__dict__.items():  # logger.info(..., extra={...})
            if key not in _STANDARD and not key.startswith("_"):
                entry[key] = value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
        if "agent_id" not in entry and "session_id" in entry and self._agent_for_session is not None:
            agent = self._agent_for_session(str(entry["session_id"]))
            if agent:
                entry["agent_id"] = agent
        if record.exc_info:
            entry["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(agent_for_session: Callable[[str], str | None] | None = None) -> None:
    """Install the root handler. uvicorn must run with ``log_config=None`` so its loggers use it."""
    as_json = os.environ.get("RELAY_LOG_FORMAT", "text").lower() == "json"
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        JsonFormatter(agent_for_session)
        if as_json
        else TextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("RELAY_LOG_LEVEL", "INFO").upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
        logger.setLevel(logging.INFO)
