"""SQLite document store: one table per kind, each row a JSON document.

The file is ``$BUS_DB_PATH`` (default ``bus.db``), or the visitor's sandbox file inside
``sandbox.use(...)``. An empty database is seeded with schedules, operator reviews and coupons.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

KINDS = ("schedules", "reviews", "coupons", "travellers", "bookings")

_lock = threading.RLock()
_seeded_paths: set[str] = set()


def db_path() -> str:
    from bus_api import sandbox

    return sandbox.current_path() or os.environ.get("BUS_DB_PATH", "bus.db")


def forget(path: str) -> None:
    """Called before a database file is deleted, so it is seeded again when next used."""
    with _lock:
        _seeded_paths.discard(path)


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
    if conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]:
        return
    from bus_api.seeds import COUPONS, build_reviews, build_schedules

    for kind, rows_ in (("schedules", build_schedules()), ("reviews", build_reviews()), ("coupons", [{**c, "id": c["code"]} for c in COUPONS])):
        for seq, row in enumerate(rows_):
            conn.execute(f"INSERT INTO {kind} (id, seq, data) VALUES (?, ?, ?)", (row["id"], seq, json.dumps(row)))


@contextmanager
def transaction() -> Iterator[None]:
    """Hold the store lock across several reads and writes (e.g. booking: seat check + insert)."""
    with _lock:
        yield


def rows(kind: str) -> list[dict[str, Any]]:
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
        conn.execute(f"INSERT OR REPLACE INTO {kind} (id, seq, data) VALUES (?, ?, ?)", (row["id"], seq[0], json.dumps(row)))
    return row


def _check(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
