"""SQLite document store for the CRM: one table per kind, each row a JSON document.

Documents (not fixed columns) keep the schema open — customers can add fields without
migrations. The file is ``$CRM_DB_PATH`` (default ``crm.db``); an empty database is seeded with
the deterministic demo data on first use.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

KINDS = ("accounts", "contacts", "deals", "activities")
ID_PREFIX = {"accounts": "ACC", "contacts": "CON", "deals": "DEAL", "activities": "ACT"}

_lock = threading.Lock()
_seeded_paths: set[str] = set()


def db_path() -> str:
    return os.environ.get("CRM_DB_PATH", "crm.db")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    with _lock:
        conn = sqlite3.connect(path)
        try:
            if path not in _seeded_paths:
                _ensure_schema_and_seed(conn)
                _seeded_paths.add(path)
            yield conn
            conn.commit()
        finally:
            conn.close()


def _ensure_schema_and_seed(conn: sqlite3.Connection) -> None:
    for kind in KINDS:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {kind} (id TEXT PRIMARY KEY, seq INTEGER, data TEXT NOT NULL)")
    if conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]:
        return
    from crm_tools_api.seeds import build_seed_data

    for kind, rows in build_seed_data().items():
        for seq, row in enumerate(rows):
            conn.execute(f"INSERT INTO {kind} (id, seq, data) VALUES (?, ?, ?)", (row["id"], seq, json.dumps(row)))


def rows(kind: str) -> list[dict[str, Any]]:
    """All documents of a kind, in insertion order."""
    _check(kind)
    with _connect() as conn:
        return [json.loads(r[0]) for r in conn.execute(f"SELECT data FROM {kind} ORDER BY seq")]


def get(kind: str, row_id: str) -> dict[str, Any] | None:
    _check(kind)
    with _connect() as conn:
        found = conn.execute(f"SELECT data FROM {kind} WHERE id = ?", (row_id,)).fetchone()
    return json.loads(found[0]) if found else None


def put(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace a document (keeps its position when replacing)."""
    _check(kind)
    with _connect() as conn:
        seq = conn.execute(f"SELECT seq FROM {kind} WHERE id = ?", (row["id"],)).fetchone()
        if seq is None:
            seq = conn.execute(f"SELECT COALESCE(MAX(seq), -1) + 1 FROM {kind}").fetchone()
        conn.execute(
            f"INSERT OR REPLACE INTO {kind} (id, seq, data) VALUES (?, ?, ?)",
            (row["id"], seq[0], json.dumps(row)),
        )
    return row


def delete(kind: str, row_id: str) -> bool:
    _check(kind)
    with _connect() as conn:
        return conn.execute(f"DELETE FROM {kind} WHERE id = ?", (row_id,)).rowcount > 0


def next_id(kind: str) -> str:
    """Next id like DEAL-2081 / CON-025, one past the highest existing number."""
    prefix = ID_PREFIX[kind]
    numbers = [int(m.group(1)) for r in rows(kind) if (m := re.fullmatch(rf"{prefix}-(\d+)", r["id"]))]
    width = 3 if kind == "contacts" else 4 if kind == "activities" else 0
    return f"{prefix}-{(max(numbers) + 1 if numbers else 1):0{width}d}"


def _check(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
