"""Gateway test defaults: no agent manifests, and a throwaway CRM database."""

from __future__ import annotations

import os
import tempfile

# Startup must not reach real tools services.
os.environ.setdefault("RELAY_AGENTS_DIR", "/nonexistent-relay-agents")
# Tests start sessions without an API key.
os.environ.setdefault("RELAY_DEV_SESSIONS", "1")
# The integration tests exercise the mortgage example as the gateway's default agent.
os.environ.setdefault("RELAY_EXAMPLE_MORTGAGE", "1")
os.environ.setdefault("RELAY_SECRETS_KEY", "test-only-secrets-key-0123456789")
# Most tests sign up and sign in straight away; email confirmation has its own tests.
os.environ.setdefault("RELAY_EMAIL_VERIFICATION", "off")
# CRM tools write to SQLite; tests must never touch a real database file.
os.environ["CRM_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="relay-crm-test-"), "crm.db")
os.environ["SHOP_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="relay-shop-test-"), "shop.db")
os.environ["BUS_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="relay-bus-test-"), "bus.db")
os.environ["STAYS_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="relay-stays-test-"), "stays.db")

import httpx  # noqa: E402
import pytest  # noqa: E402

from gateway_test_support import FakeTenantWorld, run_turn  # noqa: E402,F401


@pytest.fixture
def tenant_world(monkeypatch):
    """Route project agents' tool calls and model calls to in-process fakes."""
    from relay_gateway.core import container

    world = FakeTenantWorld()
    service = container.project_agent_service
    monkeypatch.setattr(service, "http_transport", httpx.MockTransport(world.handle))
    monkeypatch.setattr(service, "_model_provider_factory", world.provider)
    monkeypatch.setenv("RELAY_ALLOW_PRIVATE_TOOLS_URLS", "1")  # *.test hosts do not resolve
    return world


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Every test starts with empty rate-limit counters (they are per process, like the app)."""
    from relay_gateway.core import container

    clear = getattr(container.rate_limit_repository, "clear", None)
    if clear is not None:
        clear()
    yield
