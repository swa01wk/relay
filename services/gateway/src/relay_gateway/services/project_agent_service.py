"""Each project's own agents: its manifest, its tools service, its model key.

A session started with a project key runs on a runtime built only from that project's data, so
one customer's agent can never call another customer's tools or spend another's model key.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

from relay_adapter_tools_http import HttpToolExecutor
from relay_gateway.core.errors import BadRequest, Conflict, NotFound
from relay_gateway.models import OPENAI_API_KEY, ProjectAgent
from relay_gateway.repositories.project_agent_repository import ProjectAgentRepository
from relay_gateway.services.agent_service import (
    AgentManifest,
    ManifestError,
    build_manifest_runtime,
    discover_tools,
    parse_manifest_text,
)
from relay_gateway.services.secret_service import SecretService
from relay_runtime import AgentRuntime, ModelRouter
from relay_runtime.ports.model import ModelProvider

logger = logging.getLogger(__name__)

ModelProviderFactory = Callable[[str, str | None], ModelProvider]  # (api_key, model) → provider
MAX_AGENTS_PER_PROJECT = 20
MAX_PROMPT_CHARS = 40_000


def agent_view(agent: ProjectAgent) -> dict[str, Any]:
    return {
        "agent_id": agent.agent_id,
        "tools_url": agent.tools_url,
        "model": agent.model,
        "updated_at": agent.updated_at.isoformat(),
    }


def _private_urls_allowed() -> bool:
    return os.environ.get("RELAY_ALLOW_PRIVATE_TOOLS_URLS", "").lower() in ("1", "true", "yes")


async def check_tools_url(url: str) -> None:
    """Refuse URLs that would make the gateway call into its own network.

    Customers choose this URL and the gateway requests it from inside the operator's network,
    so anything resolving to a private, loopback or link-local address is rejected (unless
    ``RELAY_ALLOW_PRIVATE_TOOLS_URLS=1``, for local development).
    """
    if _private_urls_allowed():
        return
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise BadRequest("tools_url must use https")
    if not parts.hostname or parts.username or parts.password:
        raise BadRequest("tools_url must be a plain https URL without credentials")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, parts.port or 443)
    except OSError:
        raise BadRequest(f"tools_url host cannot be resolved: {parts.hostname}") from None
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise BadRequest("tools_url must be reachable from the public internet (it resolves to a private address)")


class _Entry:
    def __init__(self, runtime: AgentRuntime, closers: list[Any]) -> None:
        self.runtime = runtime
        self.closers = closers  # HTTP clients to close once no session uses the runtime


class ProjectAgentService:
    def __init__(
        self,
        agents: ProjectAgentRepository,
        secret_service: SecretService,
        *,
        model_provider_factory: ModelProviderFactory,
        is_live: Callable[[str], bool],
    ) -> None:
        self._agents = agents
        self._secrets = secret_service
        self._model_provider_factory = model_provider_factory
        self._is_live = is_live
        self._cache: dict[tuple[str, str], _Entry] = {}
        self._by_session: dict[str, _Entry] = {}
        self._retired: list[_Entry] = []
        # Tests replace this to serve a tools service in-process.
        self.http_transport: httpx.AsyncBaseTransport | None = None

    # --- definitions -------------------------------------------------------------------------

    async def push(self, project_id: str, manifest_text: str, *, system_prompt: str | None = None) -> dict[str, Any]:
        """Create or replace an agent from a manifest; fails unless its tools service answers."""
        try:
            manifest = parse_manifest_text(manifest_text, system_prompt=system_prompt)
        except ManifestError as error:
            raise BadRequest(str(error)) from None
        if len(manifest.system_prompt) > MAX_PROMPT_CHARS:
            raise BadRequest(f"system prompt is too long (max {MAX_PROMPT_CHARS} characters)")
        existing = await self._agents.of_project(project_id)
        if len(existing) >= MAX_AGENTS_PER_PROJECT and manifest.agent_id not in {a.agent_id for a in existing}:
            raise Conflict(f"a project can have at most {MAX_AGENTS_PER_PROJECT} agents")
        await check_tools_url(manifest.tools_url)
        tools = await self._discover(project_id, manifest.tools_url)

        saved = await self._agents.save(
            ProjectAgent(
                project_id, manifest.agent_id, manifest.tools_url, manifest.system_prompt, manifest.instructions,
                manifest.tool_timeout_seconds, manifest.model, datetime.now(timezone.utc),
            )  # fmt: skip
        )
        await self.invalidate(project_id)
        return {**agent_view(saved), "tools": sorted(str(t.get("name")) for t in tools if t.get("name"))}

    async def list(self, project_id: str) -> list[ProjectAgent]:
        return await self._agents.of_project(project_id)

    async def delete(self, project_id: str, agent_id: str) -> None:
        if not await self._agents.delete(project_id, agent_id):
            raise NotFound("agent not found")
        await self.invalidate(project_id)

    async def _discover(self, project_id: str, tools_url: str) -> list[dict[str, Any]]:
        signing_secret = await self._secrets.tools_signing_secret(project_id)
        try:
            return await discover_tools(
                tools_url, attempts=1, transport=self.http_transport, signing_secret=signing_secret
            )
        except ManifestError as error:
            raise BadRequest(f"{error}. The tools service must answer GET {tools_url}/tools") from None

    # --- runtimes ----------------------------------------------------------------------------

    async def runtime_for(self, project_id: str, agent_id: str) -> AgentRuntime:
        """The runtime for one of the project's agents, built on first use and then reused."""
        entry = self._cache.get((project_id, agent_id))
        if entry is None:
            entry = await self._build(project_id, agent_id)
            self._cache[(project_id, agent_id)] = entry
        return entry.runtime

    async def _build(self, project_id: str, agent_id: str) -> _Entry:
        agent = await self._agents.get(project_id, agent_id)
        if agent is None:
            raise NotFound(f"this project has no agent {agent_id!r} (add one with `relay agents push`)")
        api_key = await self._secrets.reveal(project_id, OPENAI_API_KEY)
        if not api_key:
            raise Conflict("this project has no model API key (set one with `relay secrets set openai`)")
        await check_tools_url(agent.tools_url)  # the host may have changed since the push
        tools = await self._discover(project_id, agent.tools_url)
        signing_secret = await self._secrets.tools_signing_secret(project_id)

        provider = self._model_provider_factory(api_key, agent.model)
        delegate = HttpToolExecutor(
            base_url=agent.tools_url,
            timeout_seconds=agent.tool_timeout_seconds,
            signing_secret=signing_secret,
            transport=self.http_transport,
        )
        manifest = AgentManifest(
            agent.agent_id, agent.tools_url, agent.system_prompt, agent.instructions, agent.tool_timeout_seconds
        )
        runtime = build_manifest_runtime(manifest, tools, model_router=ModelRouter(provider), delegate=delegate)
        logger.info("project agent ready agent=%s project_id=%s (%d tools)", agent_id, project_id, len(tools))
        return _Entry(runtime, [provider, delegate])

    def bind_session(self, session_id: str, project_id: str, agent_id: str) -> None:
        """Pin a new session to the runtime it started with, so a later push cannot swap an
        agent, its tools or its key under a running conversation."""
        entry = self._cache.get((project_id, agent_id))
        if entry is not None:
            self._by_session[session_id] = entry

    def runtime_of_session(self, session_id: str) -> AgentRuntime | None:
        entry = self._by_session.get(session_id)
        return entry.runtime if entry else None

    async def invalidate(self, project_id: str) -> None:
        """Forget the project's cached runtimes (its agents, key or signing secret changed)."""
        for key in [k for k in self._cache if k[0] == project_id]:
            self._retired.append(self._cache.pop(key))
        await self._release_unused()

    async def _release_unused(self) -> None:
        for session_id in [s for s in self._by_session if not self._is_live(s)]:
            del self._by_session[session_id]
        in_use = {id(entry) for entry in self._by_session.values()}
        still_used: list[_Entry] = []
        for entry in self._retired:
            if id(entry) in in_use:
                still_used.append(entry)
                continue
            for closer in entry.closers:
                await closer.aclose()
        self._retired = still_used

    async def aclose(self) -> None:
        for entry in [*self._cache.values(), *self._retired]:
            for closer in entry.closers:
                await closer.aclose()
        self._cache.clear()
        self._retired.clear()
        self._by_session.clear()
