"""Ensure protocol package has no adapter/framework leakage."""

from pathlib import Path


FORBIDDEN_TOKENS = (
    "pipecat",
    "langgraph",
    "openai",
    "deepgram",
    "mortgage",
)


def test_protocol_sources_contain_no_forbidden_imports():
    root = Path(__file__).resolve().parents[1] / "src" / "relay_protocol"
    for path in root.rglob("*.py"):
        text = path.read_text().lower()
        for token in FORBIDDEN_TOKENS:
            assert token not in text, f"{path} mentions forbidden token {token!r}"
