"""Gateway logging: tokens never reach the log; JSON lines carry session/turn/agent ids."""

from __future__ import annotations

import io
import json
import logging

from relay_gateway.logging_setup import JsonFormatter, RedactingFilter, TextFormatter, redact


def _logger(formatter: logging.Formatter) -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(formatter)
    logger = logging.getLogger(f"relay.test.{id(stream)}")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, stream


def test_redacts_tokens_in_urls_headers_and_tracebacks():
    assert redact("/ws/sessions/abc?token=s3cr3t&x=1") == "/ws/sessions/abc?token=[redacted]&x=1"
    assert redact("dev_token=abc api_key=sk-1 Authorization: Bearer sk-live-9") == (
        "dev_token=[redacted] api_key=[redacted] Authorization: Bearer [redacted]"
    )
    assert redact("turn_id=t1 tokens=42 used") == "turn_id=t1 tokens=42 used"  # not a credential

    logger, stream = _logger(TextFormatter("%(message)s"))
    # Same shape as uvicorn's access and WebSocket records: the URL is an argument.
    logger.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/dev/sessions/s1/timeline?token=s3cr3t", "1.1", 200)
    logger.info('%s - "WebSocket %s" [accepted]', "1.2.3.4:5", "/ws/sessions/s1?token=s3cr3t")
    try:
        raise RuntimeError("GET http://tools/x?api_key=s3cr3t failed")
    except RuntimeError:
        logger.exception("tool failed")
    out = stream.getvalue()
    assert "s3cr3t" not in out and "token=[redacted]" in out and "api_key=[redacted]" in out


def test_json_lines_carry_ids_and_extras():
    logger, stream = _logger(JsonFormatter(agent_for_session=lambda sid: "sales-crm" if sid == "s1" else None))
    logger.info("text turn failed session_id=%s turn_id=%s", "s1", "t9")
    logger.info("agent %s loaded", "x", extra={"agent_id": "mortgage", "tools": 17})
    logger.info("ws /ws/sessions/s2?token=s3cr3t")
    first, second, third = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["session_id"] == "s1" and first["turn_id"] == "t9" and first["agent_id"] == "sales-crm"
    assert first["level"] == "info" and first["ts"].endswith("+00:00")
    assert second["agent_id"] == "mortgage" and second["tools"] == 17
    assert "s3cr3t" not in third["message"]
