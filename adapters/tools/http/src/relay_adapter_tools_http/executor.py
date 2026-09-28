"""HTTP-backed ToolExecutor — tool URLs configured per deployment (no domain in runtime)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from relay_runtime.failure_injection import inject_tool_timeout_seconds
from relay_runtime.ports.tools import ToolExecutor


class HttpToolExecutor(ToolExecutor):
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def execute(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        del session_id
        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if tool_name == "commit_correction":
            headers["X-Mortgage-Commit-Token"] = os.environ.get(
                "RELAY_MORTGAGE_COMMIT_TOKEN",
                os.environ.get("MORTGAGE_COMMIT_TOKEN", "dev-mortgage-commit"),
            )
        timeout = inject_tool_timeout_seconds(self._timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self._base_url}/tools/{tool_name}",
                json=arguments,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
            if isinstance(body, dict):
                return body
            return {"result": body}
