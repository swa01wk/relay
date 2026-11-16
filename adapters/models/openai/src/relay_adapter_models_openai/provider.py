"""OpenAI-compatible streaming provider with deterministic mock fallback."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from relay_runtime.failure_injection import inject_model_timeout
from relay_runtime.ports.model import ModelProvider


class OpenAIProvider(ModelProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._model = (
            model
            or os.environ.get("RELAY_OPENAI_MODEL")
            or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        )
        self._base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip(
            "/"
        )
        self._cancelled: set[str] = set()
        # Some OpenAI-compatible servers reject stream_options; RELAY_OPENAI_STREAM_USAGE=0 turns it off.
        self._stream_usage = os.environ.get("RELAY_OPENAI_STREAM_USAGE", "1").lower() not in ("0", "false", "no")
        # Reasoning models think before the first token; RELAY_OPENAI_REASONING_EFFORT=low cuts voice latency.
        self._reasoning_effort = os.environ.get("RELAY_OPENAI_REASONING_EFFORT", "").strip().lower() or None
        # Tail latency: when the first chunk is this late, send the same request again and use
        # whichever answers first (costs a duplicate call only on slow requests). Unset = off.
        self._hedge_after = float(os.environ.get("RELAY_OPENAI_HEDGE_AFTER_SECS", "0") or 0) or None
        # One pooled client: reuses TCP/TLS to the API across turns and tool rounds.
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def stream_completion(
        self,
        session_id: str,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield ``{"type": "token"}`` chunks, one ``{"type": "tool_calls"}`` if the model called
        tools, and one ``{"type": "usage"}`` (token counts) when the API reports it."""
        if session_id in self._cancelled:
            self._cancelled.discard(session_id)
            return
        if inject_model_timeout():
            await asyncio.sleep(0.05)
            raise TimeoutError("RELAY_INJECT_MODEL_TIMEOUT")

        if not self._api_key:
            text = _mock_reply(messages)
            for token in _chunk_text(text):
                if session_id in self._cancelled:
                    break
                yield {"type": "token", "text": token}
            return

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        if self._stream_usage:
            # Usage arrives in a final chunk whose ``choices`` list is empty.
            body["stream_options"] = {"include_usage": True}
        usage: dict[str, Any] | None = None
        # Streamed tool calls arrive as fragments keyed by index; arguments concatenate.
        pending_calls: dict[int, dict[str, str]] = {}
        response, rest, first = await self._first_stream(headers, body)
        try:
            async for line in _chain(first, rest):
                if session_id in self._cancelled:
                    break
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                payload = json.loads(data)
                if isinstance(payload.get("usage"), dict):
                    usage = payload["usage"]
                choices = payload.get("choices") or [{}]
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield {"type": "token", "text": text}
                for fragment in delta.get("tool_calls") or []:
                    call = pending_calls.setdefault(
                        int(fragment.get("index", 0)), {"id": "", "name": "", "arguments": ""}
                    )
                    call["id"] = fragment.get("id") or call["id"]
                    function = fragment.get("function") or {}
                    call["name"] = function.get("name") or call["name"]
                    call["arguments"] += function.get("arguments") or ""
        finally:
            await response.aclose()
        if pending_calls and session_id not in self._cancelled:
            yield {"type": "tool_calls", "calls": [pending_calls[i] for i in sorted(pending_calls)]}
        if usage is not None:
            yield {
                "type": "usage",
                "model": self._model,
                "input_tokens": usage.get("prompt_tokens") or 0,
                "output_tokens": usage.get("completion_tokens") or 0,
                "cached_input_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
            }

    async def _open_stream(
        self, headers: dict[str, str], body: dict[str, Any]
    ) -> tuple[httpx.Response, AsyncIterator[str], list[str]]:
        """Start a streamed completion and read up to its first data line."""
        client = self._http()
        request = client.build_request("POST", f"{self._base_url}/chat/completions", headers=headers, json=body)
        response = await client.send(request, stream=True)
        try:
            response.raise_for_status()
            lines = response.aiter_lines()
            first: list[str] = []
            async for line in lines:
                first.append(line)
                if line.startswith("data: "):
                    break
            return response, lines, first
        except BaseException:
            await response.aclose()
            raise

    async def _first_stream(
        self, headers: dict[str, str], body: dict[str, Any]
    ) -> tuple[httpx.Response, AsyncIterator[str], list[str]]:
        """``_open_stream``, hedged: a second identical request races the first if it is slow."""
        primary = asyncio.create_task(self._open_stream(headers, body))
        if self._hedge_after is None:
            return await primary
        tasks = {primary}
        try:
            done, _ = await asyncio.wait(tasks, timeout=self._hedge_after)
            if not done:
                tasks.add(asyncio.create_task(self._open_stream(headers, body)))
            error: BaseException | None = None
            while tasks:
                done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                winners = [t for t in done if not t.cancelled() and t.exception() is None]
                for task in done:
                    if task not in winners[:1]:
                        if task in winners:
                            await task.result()[0].aclose()  # both answered at once
                        elif error is None:
                            error = task.exception()
                if winners:
                    return winners[0].result()
            assert error is not None
            raise error
        finally:
            for task in tasks:
                task.cancel()

    async def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)


async def _chain(first: list[str], rest: AsyncIterator[str]) -> AsyncIterator[str]:
    for line in first:
        yield line
    async for line in rest:
        yield line


def _mock_reply(messages: list[dict[str, Any]]) -> str:
    """Canned reply used when no API key is configured (local runs and tests)."""
    last_user = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            last_user = str(message.get("content", ""))
            break
    if "who are you" in last_user.lower():
        return "I'm a Relay demo assistant running without a model API key, so I can only echo."
    if last_user:
        return f"You said: {last_user}. (No model API key is configured, so this is a canned reply.)"
    return "Hello! No model API key is configured, so I can only give canned replies."


def _chunk_text(text: str, size: int = 12) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]
