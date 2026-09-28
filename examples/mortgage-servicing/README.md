# Mortgage servicing reference app

External consumer of Relay — **no** mortgage logic in `runtime/` or `packages/protocol`.

- `frontend/` — Next.js app (search, case, draft correction, rate history, conflict banner)
- `agent/` — `MortgageServicingAgent` (read tools, UI actions, draft state sync)
- `tools/` — FastAPI read tools + `prepare_correction` / `recalculate_correction_draft` (port 8090)
- `fixtures/` — seed JSON for demo data

See [`plans/phase-00-foundation.md`](../../plans/phase-00-foundation.md).

### Phase 8 demo phrases (@ :3000 + gateway :8080)

1. **Find Rajesh Sharma** → open MORT-2931  
2. **Prepare correction draft** (or *slow* for race testing)  
3. Edit **Effective date** in the UI **or** say **“change the date to 01/01/2026”** / **“Yeah, update.”** — must match the draft field (routed tools, not LLM-only)  
4. Navigate to rate history while a stale agent delta is in flight → **Stale agent update blocked** banner (human edit wins)

### Phase 9 demo phrases (@ :3000 + gateway :8080) — §12.1 steps 13–15

1. Complete Phase 8 draft on **MORT-2931**  
2. **Submit for approval** → approval dialog (`APPROVAL_REQUESTED`)  
3. **Approve & commit** (POC auth proof `dev-approver`) → `COMMIT_STARTED` / `COMMIT_VERIFIED`  
4. Case view reflects authoritative backend rate/EMI after verify
