"""Declarative agents: ``<agents dir>/*.yaml`` manifests + tool discovery (no Python per domain).

Manifest::

    agent_id: sales-crm
    tools_url: ${RELAY_CRM_TOOLS_URL:-http://localhost:8091}
    system_prompt_file: sales-crm.prompt.md     # or inline `system_prompt: |`
    instructions: "Pipeline by stage → bar chart; …"   # optional present_ui hints
    tool_timeout_seconds: 30                      # optional

The tools service must answer ``GET {tools_url}/tools`` with
``{"tools": [{"name", "description", "input_schema", "classification"}]}`` and run tools at
``POST {tools_url}/tools/{name}``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from relay_adapter_tools_http import HttpToolExecutor
from relay_runtime import (
    AgentRuntime,
    ModelRouter,
    RegistryToolExecutor,
    ToolClassification,
    ToolDefinition,
    ToolRegistry,
    ToolUsingAgent,
    TraceManager,
)

logger = logging.getLogger(__name__)

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_REQUIRED = ("agent_id", "tools_url")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class AgentManifest:
    agent_id: str
    tools_url: str
    system_prompt: str
    instructions: str = ""
    tool_timeout_seconds: float = 30.0
    source: str = ""


def _expand_env(value: str) -> str:
    """``${VAR}`` and ``${VAR:-default}``; unset without default → empty string."""
    return _ENV_REF.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), value)


def parse_manifest(path: Path) -> AgentManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path.name}: invalid YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path.name}: expected a mapping")
    missing = [key for key in _REQUIRED if not raw.get(key)]
    if missing:
        raise ManifestError(f"{path.name}: missing {', '.join(missing)}")

    prompt = raw.get("system_prompt")
    prompt_file = raw.get("system_prompt_file")
    if prompt_file:
        prompt_path = (path.parent / str(prompt_file)).resolve()
        if not prompt_path.is_file():
            raise ManifestError(f"{path.name}: system_prompt_file not found: {prompt_file}")
        prompt = prompt_path.read_text(encoding="utf-8")
    if not prompt or not str(prompt).strip():
        raise ManifestError(f"{path.name}: set system_prompt or system_prompt_file")

    tools_url = _expand_env(str(raw["tools_url"])).strip().rstrip("/")
    if not tools_url.startswith(("http://", "https://")):
        raise ManifestError(f"{path.name}: tools_url must be http(s), got {tools_url!r}")
    return AgentManifest(
        agent_id=str(raw["agent_id"]).strip(),
        tools_url=tools_url,
        system_prompt=str(prompt).strip(),
        instructions=str(raw.get("instructions") or "").strip(),
        tool_timeout_seconds=float(raw.get("tool_timeout_seconds") or 30.0),
        source=path.name,
    )


def registry_from_tool_specs(specs: list[dict[str, Any]]) -> ToolRegistry:
    """Build a ToolRegistry from a ``GET /tools`` response's ``tools`` list."""
    registry = ToolRegistry()
    for spec in specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        try:
            classification = ToolClassification(spec.get("classification") or "read_only")
        except ValueError:
            logger.warning("tool %s: unknown classification %r; treating as side_effecting", name, spec.get("classification"))
            classification = ToolClassification.SIDE_EFFECTING
        registry.register(
            ToolDefinition(
                name=name,
                classification=classification,
                description=str(spec.get("description") or ""),
                input_schema=spec.get("input_schema") or {"type": "object", "properties": {}},
                output_schema={"type": "object"},
            )
        )
    return registry


def build_manifest_runtime(
    manifest: AgentManifest,
    tool_specs: list[dict[str, Any]],
    *,
    model_router: ModelRouter,
    delegate: Any,
) -> AgentRuntime:
    registry = registry_from_tool_specs(tool_specs)
    agent = ToolUsingAgent(
        model_router,
        system_prompt=manifest.system_prompt,
        registry=registry,
        instructions=manifest.instructions,
    )
    return AgentRuntime(
        model_router=model_router,
        agent=agent,
        tool_executor=RegistryToolExecutor(
            registry=registry,
            delegate=delegate,
            trace_manager=TraceManager(),
            default_timeout_seconds=manifest.tool_timeout_seconds,
        ),
    )


async def discover_tools(
    tools_url: str,
    *,
    attempts: int = 10,
    delay_seconds: float = 2.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict[str, Any]]:
    """Fetch ``GET {tools_url}/tools``, retrying while the tools service starts."""
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await client.get(f"{tools_url}/tools")
                response.raise_for_status()
                tools = response.json().get("tools")
                if not isinstance(tools, list):
                    raise ManifestError(f"{tools_url}/tools did not return a 'tools' list")
                return tools
            except ManifestError:
                raise
            except Exception as exc:  # network errors while the service starts
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(delay_seconds)
    raise ManifestError(f"tool discovery failed for {tools_url}: {last_error}")


async def load_agent_manifests(
    agents_dir: Path,
    *,
    model_router: ModelRouter,
    runtimes: dict[str, AgentRuntime],
    delegates: list[Any],
    attempts: int = 10,
    delay_seconds: float = 2.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[str]:
    """Register every manifest in ``agents_dir``; returns the agent ids loaded."""
    if not agents_dir.is_dir():
        logger.info("no agent manifests directory at %s", agents_dir)
        return []
    loaded: list[str] = []
    for path in sorted([*agents_dir.glob("*.yaml"), *agents_dir.glob("*.yml")]):
        try:
            manifest = parse_manifest(path)
            if manifest.agent_id in runtimes:
                raise ManifestError(f"{path.name}: agent_id {manifest.agent_id!r} is already registered")
            specs = await discover_tools(
                manifest.tools_url, attempts=attempts, delay_seconds=delay_seconds, transport=transport
            )
        except ManifestError as exc:
            logger.error("agent manifest skipped: %s", exc)
            continue
        delegate = HttpToolExecutor(base_url=manifest.tools_url, timeout_seconds=manifest.tool_timeout_seconds)
        delegates.append(delegate)
        runtimes[manifest.agent_id] = build_manifest_runtime(
            manifest, specs, model_router=model_router, delegate=delegate
        )
        loaded.append(manifest.agent_id)
        logger.info("agent %s loaded from %s (%d tools)", manifest.agent_id, path.name, len(specs))
    return loaded
