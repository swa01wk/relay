"""Per-visitor demo data ("sandboxes") for the public Experience Center.

When ``VNB_SANDBOX_DIR`` is set, a session started for an end user whose id looks like
``sandbox_<random>`` reads and writes its own SQLite file, created from the demo data on first
use. Visitors never see each other's changes; files untouched for ``VNB_SANDBOX_TTL_SECONDS``
(default 2 h) are deleted, and at most ``VNB_SANDBOX_MAX`` (default 500) are kept.

The sandbox id is the customer's user id:
- tool calls: the signed ``X-Relay-User`` header (the bank site's server starts the session with
  ``user = {"id": "sandbox_…"}``), so the browser cannot pick another visitor's data;
- the banking API (``/api/…``) and ``POST /sandbox/reset``: ``X-Vnb-User`` / ``X-Sandbox-Id``,
  sent by the bank site's server from its own cookie. The ids are random, so knowing one is the
  only way in.
Other user ids use the shared ``VNB_DB_PATH`` (each customer's accounts are still their own).
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_ID = re.compile(r"sandbox_[A-Za-z0-9_-]{16,64}")
_current: ContextVar[Path | None] = ContextVar("vnb_sandbox_path", default=None)
_last_sweep = 0.0


def directory() -> Path | None:
    raw = os.environ.get("VNB_SANDBOX_DIR", "").strip()
    return Path(raw) if raw else None


def valid_id(value: str | None) -> str | None:
    """``value`` when sandboxes are on and it is a well-formed sandbox id, else ``None``."""
    if not value or directory() is None:
        return None
    return value if _ID.fullmatch(value) else None


def path_for(sandbox_id: str) -> Path:
    folder = directory()
    assert folder is not None and _ID.fullmatch(sandbox_id)
    return folder / f"{sandbox_id}.db"


def current_path() -> str | None:
    path = _current.get()
    return str(path) if path else None


@contextmanager
def use(sandbox_id: str | None) -> Iterator[None]:
    """Route database access in this block to the sandbox's file (no-op without an id)."""
    sandbox_id = valid_id(sandbox_id)
    if sandbox_id is None:
        yield
        return
    path = path_for(sandbox_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    sweep()
    if path.exists():
        os.utime(path)  # reads count as activity too
    token = _current.set(path)
    try:
        yield
    finally:
        _current.reset(token)


def reset(sandbox_id: str | None) -> bool:
    """Delete a sandbox's data; its next use starts again from the seed."""
    sandbox_id = valid_id(sandbox_id)
    if sandbox_id is None:
        return False
    from vnb_api import db

    path = path_for(sandbox_id)
    db.forget(str(path))
    path.unlink(missing_ok=True)
    return True


def sweep(*, now: float | None = None, force: bool = False) -> None:
    """Remove expired sandboxes and keep at most ``VNB_SANDBOX_MAX`` (at most once a minute)."""
    global _last_sweep
    folder = directory()
    now = now if now is not None else time.time()
    if folder is None or not folder.is_dir() or (not force and now - _last_sweep < 60):
        return
    _last_sweep = now
    from vnb_api import db

    ttl = float(os.environ.get("VNB_SANDBOX_TTL_SECONDS", "7200"))
    keep = int(os.environ.get("VNB_SANDBOX_MAX", "500"))
    files = sorted(folder.glob("sandbox_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for index, path in enumerate(files):
        if index >= keep or now - path.stat().st_mtime > ttl:
            db.forget(str(path))
            path.unlink(missing_ok=True)
