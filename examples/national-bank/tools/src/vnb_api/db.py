"""SQLite document store: one table per kind, each row a JSON document that belongs to one customer.

Every row has ``user_id`` and an ``id`` that is unique per customer (``TXN-100042``, ``BEN-03``…),
so two customers' data never collide in the shared file. The file is ``$VNB_DB_PATH`` (default
``vnb.db``), or the visitor's sandbox file inside ``sandbox.use(...)``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

KINDS = ("customers", "accounts", "transactions", "beneficiaries", "deposits", "loans", "applications", "cards", "requests", "complaints",
         "enrolments", "billers", "standing", "tax_payments", "mf_holdings", "nps", "lockers", "positive_pay")

_lock = threading.RLock()
_ready_paths: set[str] = set()


def db_path() -> str:
    from vnb_api import sandbox

    return sandbox.current_path() or os.environ.get("VNB_DB_PATH", "vnb.db")


def forget(path: str) -> None:
    """Called before a database file is deleted."""
    with _lock:
        _ready_paths.discard(path)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    with _lock:
        conn = sqlite3.connect(path)
        try:
            if path not in _ready_paths:
                for kind in KINDS:
                    conn.execute(
                        f"CREATE TABLE IF NOT EXISTS {kind} (user_id TEXT NOT NULL, id TEXT NOT NULL, seq INTEGER, data TEXT NOT NULL, "
                        "PRIMARY KEY (user_id, id))"
                    )
                _ready_paths.add(path)
            yield conn
            conn.commit()
        finally:
            conn.close()


@contextmanager
def transaction() -> Iterator[None]:
    """Hold the store lock across several reads and writes (e.g. a transfer: balance check + insert)."""
    with _lock:
        yield


def rows(kind: str, user_id: str) -> list[dict[str, Any]]:
    _check(kind)
    with _connect() as conn:
        return [json.loads(r[0]) for r in conn.execute(f"SELECT data FROM {kind} WHERE user_id = ? ORDER BY seq", (user_id,))]


def get(kind: str, user_id: str, row_id: str) -> dict[str, Any] | None:
    _check(kind)
    with _connect() as conn:
        found = conn.execute(f"SELECT data FROM {kind} WHERE user_id = ? AND id = ?", (user_id, row_id)).fetchone()
    return json.loads(found[0]) if found else None


def put(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace a customer's document (keeps its position when replacing)."""
    _check(kind)
    with _connect() as conn:
        key = (row["user_id"], row["id"])
        seq = conn.execute(f"SELECT seq FROM {kind} WHERE user_id = ? AND id = ?", key).fetchone()
        if seq is None:
            seq = conn.execute(f"SELECT COALESCE(MAX(seq), -1) + 1 FROM {kind} WHERE user_id = ?", (row["user_id"],)).fetchone()
        conn.execute(f"INSERT OR REPLACE INTO {kind} (user_id, id, seq, data) VALUES (?, ?, ?, ?)", (*key, seq[0], json.dumps(row)))
    return row


def delete(kind: str, user_id: str, row_id: str) -> None:
    _check(kind)
    with _connect() as conn:
        conn.execute(f"DELETE FROM {kind} WHERE user_id = ? AND id = ?", (user_id, row_id))


def put_many(kind: str, items: list[dict[str, Any]]) -> None:
    """Insert many new documents in one go (seeding)."""
    _check(kind)
    with _connect() as conn:
        for row in items:
            seq = conn.execute(f"SELECT COALESCE(MAX(seq), -1) + 1 FROM {kind} WHERE user_id = ?", (row["user_id"],)).fetchone()
            conn.execute(f"INSERT OR REPLACE INTO {kind} (user_id, id, seq, data) VALUES (?, ?, ?, ?)",
                         (row["user_id"], row["id"], seq[0], json.dumps(row)))


def _check(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
