#!/usr/bin/env python3
"""Export session timeline JSON for evals / CI artifacts (Phase 10)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from relay_runtime.memory_event_store import MemoryEventStore
from relay_runtime.session_timeline import build_session_timeline


async def _from_memory(session_id: str) -> dict:
    store = MemoryEventStore()
    events = await store.list_for_session(session_id)
    return build_session_timeline(events)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Relay session timeline")
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--from-store",
        choices=("memory", "gateway"),
        default="gateway",
        help="memory = empty stub; use gateway URL for real export",
    )
    parser.add_argument("--gateway-url", default="http://localhost:8080")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    if args.from_store == "memory":
        timeline = asyncio.run(_from_memory(args.session_id))
    else:
        import urllib.request

        if not args.token:
            print("gateway export requires --token (dev token)", file=sys.stderr)
            return 2
        url = (
            f"{args.gateway_url.rstrip('/')}/dev/sessions/{args.session_id}/timeline"
            f"?token={args.token}"
        )
        with urllib.request.urlopen(url) as resp:
            timeline = json.loads(resp.read().decode())

    json.dump(timeline, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
