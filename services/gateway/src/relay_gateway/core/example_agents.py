"""The mortgage-servicing example as the gateway's default agent — for demos, never production.

Enabled with ``RELAY_EXAMPLE_MORTGAGE=1`` (the dev compose stack and the tests set it). This is
the only gateway module that knows an example domain; the imports are local so a production
image does not need the example packages installed.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from relay_adapter_tools_http import HttpToolExecutor
from relay_runtime import ModelRouter, ToolRegistry
from relay_runtime.ports.agent import AgentAdapter
from relay_runtime.ports.tools import ToolExecutor


def enabled() -> bool:
    return os.environ.get("RELAY_EXAMPLE_MORTGAGE", "").lower() in ("1", "true", "yes")


def _commit_headers(tool_name: str) -> dict[str, str]:
    # The example tools service requires this token on its commit endpoint.
    if tool_name != "commit_correction":
        return {}
    token = os.environ.get("RELAY_MORTGAGE_COMMIT_TOKEN", os.environ.get("MORTGAGE_COMMIT_TOKEN", "dev-mortgage-commit"))
    return {"X-Mortgage-Commit-Token": token}


def build(
    model_router: ModelRouter,
    *,
    user_for_session: Callable[[str], dict[str, Any] | None] | None = None,
) -> tuple[AgentAdapter, ToolRegistry, ToolExecutor]:
    """Agent, tool registry and tool executor for the example. ``user_for_session`` sends the
    session's end user (``X-Relay-User``) to the tools service, which keys sandbox data on it."""
    from relay_mortgage_agent import MortgageServicingAgent
    from relay_mortgage_agent.tool_definitions import register_mortgage_tools
    from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor

    registry = ToolRegistry()
    register_mortgage_tools(registry)
    url = os.environ.get("RELAY_MORTGAGE_TOOLS_URL", "").strip()
    delegate: ToolExecutor = (
        HttpToolExecutor(base_url=url, headers_for_tool=_commit_headers, user_for_session=user_for_session)
        if url
        else LocalMortgageToolExecutor()
    )
    return MortgageServicingAgent(model_router), registry, delegate
