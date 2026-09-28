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

    async def stream_completion(
        self,
        session_id: str,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del tools
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
        async with httpx.AsyncClient(timeout=120.0) as client:
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
                    delta = payload.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield {"type": "token", "text": text}

    async def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)


def _mock_reply(messages: list[dict[str, Any]]) -> str:
    last_user = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            last_user = str(message.get("content", ""))
            break
    lowered = last_user.lower()
    if "who are you" in lowered:
        return (
            "I'm the mortgage servicing reference assistant for this POC. "
            "I can help with general questions about your account."
        )
    if last_user:
        return f"You said: {last_user}. How can I help you with your mortgage today?"
    return "Hello! How can I help you with your mortgage servicing questions today?"


def _chunk_text(text: str, size: int = 12) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]
