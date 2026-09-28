"""Pytest defaults for deterministic voice turn tests."""

from __future__ import annotations

import os

os.environ.setdefault("RELAY_UTTERANCE_COMMIT_DELAY_MS", "0")
os.environ.setdefault("RELAY_STT_FINAL_ENDPOINT_MS", "0")
