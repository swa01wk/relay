"""Minimal conversation context for text turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextManager:
    """Append-only transcript plus optional semantic state slot."""

    messages: list[dict[str, str]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    state_version: int = 0
    active_turn_id: str | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        if text:
            self.messages.append({"role": "assistant", "content": text})

    def commit_assistant_heard(self, *, generated_text: str, heard_text: str) -> None:
        """Persist heard-only assistant content after barge-in (§7.2)."""
        if heard_text:
            self.append_assistant(heard_text)
        elif generated_text:
            self.append_assistant(generated_text)

    def as_chat_messages(self) -> list[dict[str, str]]:
        return list(self.messages)

    def apply_snapshot(self, snapshot: dict[str, Any]) -> int:
        """Replace semantic state and bump monotonic version (human edits win)."""
        self.state = dict(snapshot)
        self.state_version += 1
        return self.state_version

    def apply_patch(self, patch: list[dict[str, Any]]) -> int:
        """Merge agent patch ops into state and bump version."""
        merged = dict(self.state)
        for op in patch:
            key = str(op.get("key", ""))
            if not key:
                continue
            if op.get("op") == "remove":
                merged.pop(key, None)
            else:
                merged[key] = op.get("value")
        self.state = merged
        self.state_version += 1
        return self.state_version

    def state_summary_for_agent(self) -> dict[str, Any]:
        return {
            "state_version": self.state_version,
            "state": dict(self.state),
        }

    def begin_turn(self, turn_id: str) -> None:
        """Mark the active turn for stale tool result suppression (§6.3, §7.3)."""
        self.active_turn_id = turn_id

    def merge_tool_result(
        self,
        *,
        turn_id: str,
        tool_call_id: str,
        tool_name: str,
        result: dict[str, Any],
    ) -> bool:
        if self.active_turn_id != turn_id:
            return False
        self.tool_results.append(
            {
                "turn_id": turn_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "result": dict(result),
            }
        )
        return True

    def tool_results_for_agent(self) -> list[dict[str, Any]]:
        return list(self.tool_results)
