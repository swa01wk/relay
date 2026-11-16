"""Per-visitor demo data ("sandboxes") for the public Experience Center.

With ``MORTGAGE_SANDBOXES=1``, a session started for an end user whose id looks like
``sandbox_<random>`` (signed ``X-Relay-User`` header) gets its own in-memory copy of the seed
data, so visitors never see each other's corrections. Copies idle for
``MORTGAGE_SANDBOX_TTL_SECONDS`` (default 2 h) are dropped, and at most ``MORTGAGE_SANDBOX_MAX``
(default 500) are kept. Without a sandbox id everything uses the shared seed data as before.
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from mortgage_tools_api import seeds

_ID = re.compile(r"sandbox_[A-Za-z0-9_-]{16,64}")


@dataclass
class Data:
    customers: list[dict[str, Any]]
    mortgages: dict[str, dict[str, Any]]
    payments: dict[str, list[dict[str, Any]]]
    rates: dict[str, list[dict[str, Any]]]
    audit: dict[str, list[dict[str, Any]]]
    receipts: dict[str, dict[str, Any]] = field(default_factory=dict)


SHARED = Data(
    seeds.CUSTOMERS, seeds.MORTGAGES, seeds.PAYMENTS_BY_MORTGAGE, seeds.RATE_HISTORY_BY_MORTGAGE, seeds.AUDIT_BY_MORTGAGE
)
_PRISTINE = copy.deepcopy(SHARED)  # taken at import, before any commit changes SHARED
_sandboxes: OrderedDict[str, tuple[Data, float]] = OrderedDict()
_current: ContextVar[Data | None] = ContextVar("mortgage_sandbox", default=None)


def enabled() -> bool:
    return os.environ.get("MORTGAGE_SANDBOXES", "").lower() in ("1", "true", "yes")


def valid_id(value: str | None) -> str | None:
    if not value or not enabled():
        return None
    return value if _ID.fullmatch(value) else None


def id_from_user_header(raw: str | None) -> str | None:
    """The sandbox id in an ``X-Relay-User`` header value (``{"id": "sandbox_…"}``), if any."""
    if not raw:
        return None
    try:
        user = json.loads(raw)
    except ValueError:
        return None
    return valid_id(str(user.get("id"))) if isinstance(user, dict) else None


def data() -> Data:
    """The data the current request works on."""
    return _current.get() or SHARED


@contextmanager
def use(sandbox_id: str | None) -> Iterator[None]:
    sandbox_id = valid_id(sandbox_id)
    if sandbox_id is None:
        yield
        return
    token = _current.set(_get_or_create(sandbox_id))
    try:
        yield
    finally:
        _current.reset(token)


def reset(sandbox_id: str | None) -> bool:
    sandbox_id = valid_id(sandbox_id)
    if sandbox_id is None:
        return False
    _sandboxes.pop(sandbox_id, None)
    return True


def _get_or_create(sandbox_id: str, *, now: float | None = None) -> Data:
    now = now if now is not None else time.time()
    ttl = float(os.environ.get("MORTGAGE_SANDBOX_TTL_SECONDS", "7200"))
    keep = int(os.environ.get("MORTGAGE_SANDBOX_MAX", "500"))
    for key in [k for k, (_, used) in _sandboxes.items() if now - used > ttl]:
        del _sandboxes[key]
    found = _sandboxes.pop(sandbox_id, None)
    sandbox = found[0] if found else copy.deepcopy(_PRISTINE)
    _sandboxes[sandbox_id] = (sandbox, now)  # most recently used last
    while len(_sandboxes) > keep:
        _sandboxes.popitem(last=False)
    return sandbox
