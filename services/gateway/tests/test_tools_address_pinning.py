"""Every call to a customer's tools host re-checks where it points and connects only there."""

from __future__ import annotations

import httpx
import pytest

from relay_adapter_tools_http import HttpToolExecutor
from relay_gateway.core.errors import BadRequest
from relay_gateway.services import project_agent_service
from relay_gateway.services.project_agent_service import public_address


@pytest.mark.asyncio
async def test_calls_go_to_the_checked_address_with_the_real_name_for_tls():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    async def guard(host: str, port: int) -> str:
        assert (host, port) == ("tools.example.com", 443)
        return "93.184.216.34"

    executor = HttpToolExecutor(base_url="https://tools.example.com/api", address_guard=guard,
                                transport=httpx.MockTransport(handler))
    assert await executor.execute("s1", tool_name="list_orders", arguments={}) == {"ok": True}
    (request,) = seen
    assert str(request.url) == "https://93.184.216.34/api/tools/list_orders"  # connects to the checked IP
    assert request.headers["Host"] == "tools.example.com"  # the service still sees its own name
    assert request.extensions["sni_hostname"] == "tools.example.com"  # and TLS verifies that name
    await executor.aclose()


@pytest.mark.asyncio
async def test_a_host_that_now_points_inside_the_network_is_refused_on_the_next_call():
    answers = iter(["93.184.216.34", "10.0.0.5"])  # public at push time, rebound later

    async def resolve(host, port, type=None):  # stands in for DNS
        return [(None, None, None, None, (next(answers), port))]

    loop_resolve = project_agent_service.asyncio.get_running_loop().getaddrinfo
    project_agent_service.asyncio.get_running_loop().getaddrinfo = resolve  # type: ignore[method-assign]
    try:
        assert await public_address("tools.example.com", 443) == "93.184.216.34"
        with pytest.raises(BadRequest, match="private address"):
            await public_address("tools.example.com", 443)
    finally:
        project_agent_service.asyncio.get_running_loop().getaddrinfo = loop_resolve  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_private_and_unresolvable_hosts_are_refused():
    for host in ("127.0.0.1", "169.254.169.254", "10.1.2.3", "::1"):
        with pytest.raises(BadRequest):
            await public_address(host, 443)
    with pytest.raises(BadRequest, match="cannot be resolved"):
        await public_address("no-such-host.invalid", 443)
