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
        if self._stream_usage:
            # Usage arrives in a final chunk whose ``choices`` list is empty.
            body["stream_options"] = {"include_usage": True}
        usage: dict[str, Any] | None = None
        # Streamed tool calls arrive as fragments keyed by index; arguments concatenate.
        pending_calls: dict[int, dict[str, str]] = {}
        client = self._http()
        async with client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            headers=headers,
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
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

    async def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)


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
