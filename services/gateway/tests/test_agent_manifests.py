"""Declarative agents: manifest parsing, tool discovery, registration and failure handling."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from relay_adapter_models_openai import OpenAIProvider
from relay_gateway.services.agent_service import ManifestError, load_agent_manifests, parse_manifest, registry_from_tool_specs
from relay_runtime import ModelRouter

REPO = Path(__file__).resolve().parents[3]
TOOLS = [
    {"name": "list_deals", "description": "Deals", "input_schema": {"type": "object", "properties": {}}, "classification": "read_only"},
    {"name": "update_stage", "description": "Change a deal stage", "input_schema": {"type": "object"}, "classification": "side_effecting"},
    {"name": "weird", "description": "?", "classification": "unknown_kind"},
]


def _tools_transport(tools: list[dict], seen: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/tools":
            return httpx.Response(200, json={"tools": tools})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _write(tmp: Path, name: str, body: str) -> None:
    (tmp / name).write_text(body, encoding="utf-8")

def test_repo_sales_crm_manifest_parses(monkeypatch):
    monkeypatch.setenv("RELAY_CRM_TOOLS_URL", "http://crm-tools:8091")
    manifest = parse_manifest(REPO / "agents" / "sales-crm.yaml")
    assert manifest.agent_id == "sales-crm"
    assert manifest.tools_url == "http://crm-tools:8091"
    assert "sales assistant" in manifest.system_prompt
    assert "bar chart" in manifest.instructions


def test_env_default_used_when_var_unset(monkeypatch):
    monkeypatch.delenv("RELAY_CRM_TOOLS_URL", raising=False)
    assert parse_manifest(REPO / "agents" / "sales-crm.yaml").tools_url == "http://localhost:8091"


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("agent_id: x\n", "missing tools_url"),
        ("agent_id: x\ntools_url: http://t\n", "system_prompt"),
        ("agent_id: x\ntools_url: ftp://t\nsystem_prompt: hi\n", "must be http"),
        ("agent_id: x\ntools_url: http://t\nsystem_prompt_file: nope.md\n", "not found"),
        ("- just\n- a list\n", "expected a mapping"),
    ],
)
def test_invalid_manifests_are_rejected(tmp_path, body, error):
    _write(tmp_path, "bad.yaml", body)
    with pytest.raises(ManifestError, match=error):
        parse_manifest(tmp_path / "bad.yaml")


def test_registry_classifications_fail_safe():
    registry = registry_from_tool_specs(TOOLS)
    assert not registry.is_side_effecting("list_deals")
    assert registry.is_side_effecting("update_stage")
    assert registry.is_side_effecting("weird")  # unknown classification is treated as side-effecting


@pytest.mark.asyncio
async def test_load_registers_agents_and_skips_broken_ones(tmp_path):
    _write(tmp_path, "good.yaml", "agent_id: crm\ntools_url: http://tools.test\nsystem_prompt: You help with deals.\n")
    _write(tmp_path, "broken.yaml", "agent_id: [unclosed\n")
    _write(tmp_path, "dupe.yml", "agent_id: crm\ntools_url: http://tools.test\nsystem_prompt: again\n")
    seen: list[str] = []
    runtimes: dict = {}
    delegates: list = []

    loaded = await load_agent_manifests(
        tmp_path,
        model_router=ModelRouter(OpenAIProvider(api_key=None)),
        runtimes=runtimes,
        delegates=delegates,
        attempts=1,
        transport=_tools_transport(TOOLS, seen),
    )

    assert loaded == ["crm"]
    assert seen == ["http://tools.test/tools"]
    agent = runtimes["crm"].agent
    assert agent.model_tool_names == frozenset({"list_deals"})  # side-effecting tools never reach the model
    assert len(delegates) == 1


@pytest.mark.asyncio
async def test_unreachable_tools_service_skips_agent(tmp_path):
    _write(tmp_path, "a.yaml", "agent_id: a\ntools_url: http://down.test\nsystem_prompt: hi\n")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    runtimes: dict = {}
    loaded = await load_agent_manifests(
        tmp_path,
        model_router=ModelRouter(OpenAIProvider(api_key=None)),
        runtimes=runtimes,
        delegates=[],
        attempts=2,
        delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    assert loaded == [] and runtimes == {}


def test_crm_tools_service_serves_discovery():
    from fastapi.testclient import TestClient

    from crm_tools_api.main import app

    tools = TestClient(app).get("/tools").json()["tools"]
    assert {t["name"] for t in tools} >= {"list_deals", "get_pipeline_summary", "get_rep_performance"}
    assert all(t["input_schema"]["type"] == "object" for t in tools)
    by_class: dict[str, set[str]] = {}
    for tool in tools:
        by_class.setdefault(tool["classification"], set()).add(tool["name"])
    assert set(by_class) == {"read_only", "side_effecting"}
    assert len(by_class["read_only"]) == 10
    assert by_class["side_effecting"] == {
        "create_account", "create_contact", "update_contact", "create_deal", "update_deal", "delete_deal", "log_activity",
    }
    json.dumps(tools)
