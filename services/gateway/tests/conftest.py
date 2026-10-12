"""Gateway test defaults: no agent manifests, and a throwaway CRM database."""

from __future__ import annotations

import os
import tempfile

# Startup must not reach real tools services.
os.environ.setdefault("RELAY_AGENTS_DIR", "/nonexistent-relay-agents")
# CRM tools write to SQLite; tests must never touch a real database file.
os.environ["CRM_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="relay-crm-test-"), "crm.db")
