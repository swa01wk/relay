"""Agents defined per project (``relay agents push``)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime, timezone

from relay_gateway.models import ProjectAgent
from relay_gateway.repositories.database import Database


class ProjectAgentRepository(ABC):
    @abstractmethod
    async def save(self, agent: ProjectAgent) -> ProjectAgent:
        """Create or replace the project's agent with this id."""

    @abstractmethod
    async def get(self, project_id: str, agent_id: str) -> ProjectAgent | None: ...

    @abstractmethod
    async def of_project(self, project_id: str) -> list[ProjectAgent]: ...

    @abstractmethod
    async def delete(self, project_id: str, agent_id: str) -> bool: ...


class MemoryProjectAgentRepository(ProjectAgentRepository):
    def __init__(self) -> None:
        self._agents: dict[tuple[str, str], ProjectAgent] = {}

    async def save(self, agent: ProjectAgent) -> ProjectAgent:
        saved = replace(agent, updated_at=datetime.now(timezone.utc))
        self._agents[(agent.project_id, agent.agent_id)] = saved
        return saved

    async def get(self, project_id: str, agent_id: str) -> ProjectAgent | None:
        return self._agents.get((project_id, agent_id))

    async def of_project(self, project_id: str) -> list[ProjectAgent]:
        return sorted((a for a in self._agents.values() if a.project_id == project_id), key=lambda a: a.agent_id)

    async def delete(self, project_id: str, agent_id: str) -> bool:
        return self._agents.pop((project_id, agent_id), None) is not None


def _agent(row) -> ProjectAgent:
    return ProjectAgent(
        row["project_id"], row["agent_id"], row["tools_url"], row["system_prompt"], row["instructions"],
        row["tool_timeout_seconds"], row["model"], row["updated_at"],
    )  # fmt: skip


class PostgresProjectAgentRepository(ProjectAgentRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, agent: ProjectAgent) -> ProjectAgent:
        row = await (await self._db.pool()).fetchrow(
            """
            INSERT INTO relay_project_agents
                (project_id, agent_id, tools_url, system_prompt, instructions, tool_timeout_seconds, model)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (project_id, agent_id) DO UPDATE SET
                tools_url = EXCLUDED.tools_url, system_prompt = EXCLUDED.system_prompt,
                instructions = EXCLUDED.instructions, tool_timeout_seconds = EXCLUDED.tool_timeout_seconds,
                model = EXCLUDED.model, updated_at = NOW()
            RETURNING *
            """,
            agent.project_id, agent.agent_id, agent.tools_url, agent.system_prompt, agent.instructions,
            agent.tool_timeout_seconds, agent.model,
        )  # fmt: skip
        return _agent(row)

    async def get(self, project_id: str, agent_id: str) -> ProjectAgent | None:
        row = await (await self._db.pool()).fetchrow(
            "SELECT * FROM relay_project_agents WHERE project_id = $1 AND agent_id = $2", project_id, agent_id
        )
        return _agent(row) if row else None

    async def of_project(self, project_id: str) -> list[ProjectAgent]:
        rows = await (await self._db.pool()).fetch(
            "SELECT * FROM relay_project_agents WHERE project_id = $1 ORDER BY agent_id", project_id
        )
        return [_agent(row) for row in rows]

    async def delete(self, project_id: str, agent_id: str) -> bool:
        status = await (await self._db.pool()).execute(
            "DELETE FROM relay_project_agents WHERE project_id = $1 AND agent_id = $2", project_id, agent_id
        )
        return status.endswith(" 1")
