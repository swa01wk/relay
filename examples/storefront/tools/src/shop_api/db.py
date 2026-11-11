"""SQLite document store: one table per kind, each row a JSON document.

The file is ``$SHOP_DB_PATH`` (default ``shop.db``), or the visitor's sandbox file inside
``sandbox.use(...)``. An empty database is seeded with the catalog, reviews and coupons.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

KINDS = ("products", "reviews", "coupons", "shoppers", "carts", "orders", "wishlists")

_lock = threading.RLock()
_seeded_paths: set[str] = set()


def db_path() -> str:
    from shop_api import sandbox

    return sandbox.current_path() or os.environ.get("SHOP_DB_PATH", "shop.db")


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
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
        return
    from shop_api.seeds import COUPONS, build_products, build_reviews

    products = build_products()
    reviews = build_reviews(products)
    for product in products:
        mine = [r["rating"] for r in reviews if r["product_id"] == product["id"]]
        product["rating"] = round(sum(mine) / len(mine), 1) if mine else 0.0
        product["review_count"] = len(mine)
    for kind, rows in (("products", products), ("reviews", reviews), ("coupons", [{**c, "id": c["code"]} for c in COUPONS])):
        for seq, row in enumerate(rows):
            conn.execute(f"INSERT INTO {kind} (id, seq, data) VALUES (?, ?, ?)", (row["id"], seq, json.dumps(row)))


@contextmanager
def transaction() -> Iterator[None]:
    """Hold the store lock across several reads and writes (e.g. checkout: stock + order + cart)."""
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


def count(kind: str) -> int:
    _check(kind)
    with _connect() as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {kind}").fetchone()[0])


def _check(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
