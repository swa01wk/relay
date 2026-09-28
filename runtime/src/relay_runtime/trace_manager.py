"""Correlation / trace ID helpers."""

from uuid import uuid4


class TraceManager:
    def new_trace_id(self) -> str:
        return str(uuid4())

    def new_tool_call_id(self) -> str:
        return str(uuid4())

    def new_correlation_id(self) -> str:
        return str(uuid4())

    def link(self, trace_id: str, *, span_id: str | None = None) -> dict[str, str]:
        return {"trace_id": trace_id, "span_id": span_id or str(uuid4())}
