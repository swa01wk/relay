# Voice UAT script & issue log (mortgage POC @ :3000)

Operator checklist for **one pass** after `docker compose -f infra/docker/docker-compose.yml up -d --build`.  
Technical reference: [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md) · Gate tests: [TESTING.md](./TESTING.md).

**Prerequisite:** **Connect** → **Connect voice**; mic level bar should move when you speak.

---

## Test script (copy-paste queries)

| # | Say or Send | Expect |
|---|-------------|--------|
| 1 | `Hello?` / `Can you hear me?` / `Who are you?` | Spoken replies; `SPEECH_STARTED` in event log |
| 2 | `Find Rajesh Sharma` or `Let's do it for Rajesh Sharma` | `search_customer` → **MORT-2931** case view |
| 3 | `What is his email?` | **rajesh.sharma@example.com** + speech |
| 4 | `Compare last 3 months payments` | `get_payments`; payment summary |
| 5 | `Compare payments and rate history` | Parallel tools + activity (Phase 6); rate view optional |
| 6 | Long: `Explain in detail why his EMI increased…` | Long speech → **barge-in** mid-sentence → `INTERRUPTION_DETECTED` |
| 7 | *(wait for agent to finish speaking between turns)* `Show rate history` | `get_rate_history` → **rate-history-view** (6.125%) |
| 8 | `Explain that rate history` | Spoken summary matching UI rows |
| 9 | **Disconnect voice** → Send `Who are you?` | Text only, no `SPEECH_*` |
| 10 | Reconnect voice → **Mute** → Send short question | Text + spoken reply (mic off) |
| 11 | Prepare correction draft → `Change it to March, not January` (voice or text) | Effective date **2025-03-01** on screen; reply is user-facing only (see [UAT-006](#uat-006)) |

**Event audit** (replace `<session_id>` from UI):

```bash
docker exec docker-postgres-1 psql -U relay -d relay -c \
  "SELECT sequence, type, metadata->>'turn_id' FROM relay_events WHERE session_id='<session_id>' AND type IN ('SPEECH_STARTED','INTERRUPTION_DETECTED','TOOL_CALL_STARTED','TURN_STARTED') ORDER BY sequence;"
```

---

## Run log — 2026-09-25 (session `f20c94f8-5ca6-4bbb-b7c0-003bf8a8c67c`)

| # | Query (STT/UI) | Voice pipeline | Agent / UI | Notes |
|---|------------------|----------------|------------|-------|
| 1–3 | Hello, hear me, who are you | **Pass** — `SPEECH_STARTED` each turn | OK | Opening script |
| — | How many customers? | **Pass** — spoke | **Pass** — declined full count | Expected (no list tool) |
| 4 | Rajesh Sharma search | **Pass** — spoke | **Pass** — MORT-2931 | `search_customer` |
| 5 | Explain **EMI history** | **Pass** — spoke then **interrupt** | **Gap** — generic EMI essay, no `get_payments` / `get_rate_history` | See [UAT-001](#uat-001) |
| 6 | No — email ID | **Pass** — `SPEECH_STARTED` after prior interrupt | **Pass** — correct email | Short speak + 2nd interrupt (see [UAT-002](#uat-002)) |
| 7 | Similar idea | **Pass** | **Pass** — CUST-1001 | |
| 8 | Compare payments… (“latest to first market”) | **Pass** — spoke | **Partial** — `get_payments` only | STT garble; no rate leg — [UAT-003](#uat-003) |

**Platform regression validated this run:** TTS on **every** turn including turns after `INTERRUPTION_DETECTED` ([D-004-004](./DECISIONS.md#d-004-004-tts-cancel-vs-next-utterance)).

**Not exercised this run:** rate history UI (#7–8 script), disconnect-voice text-only, mute+Send, full §12.1 steps 7–9 narrative.

---

## Run log — 2026-09-25 (session `fbcb8c7f-56e3-49a0-93b3-5cc484b7274d`, Phase 8 draft)

| # | Query (STT/UI) | Voice pipeline | Agent / UI | Notes |
|---|------------------|----------------|------------|-------|
| — | Prepare correction + change effective date (voice) | **Pass** — turns + interrupt OK | **Gap** — agent said it could not sync UI / cited “routed handler”; date stayed **2025-01-01** while transcript claimed March | [UAT-006](#uat-006); conflict banner OK when human edited during slow update |
| — | `What else can you do?` / thanks | **Pass** | **Pass** — no tool leak in reply | |
| — | Case view + long EMI factors | **Pass** | **Partial** — helpful copy; STT garble on dates (“first twenty twenty five”) | Transcription tuning separate from guard rails |

**Patch (same day):** mortgage agent guard rails (`system_prompt.txt`, `response_guardrails.py`, routed month/date on draft). **Re-run script row #11** after `docker compose … up -d --build` before closing UAT-006.

---

## Open issues (track until closed)

| ID | Area | Summary | Owner / phase | Status |
|----|------|---------|---------------|--------|
| [UAT-001](#uat-001) | Agent | “EMI history” → generic LLM copy instead of seeded data or explicit “current EMI only” | Mortgage agent prompt / tools · Phase 11 or agent patch | Open |
| [UAT-002](#uat-002) | UX | User barge-in during short TTS (email) — hard to hear full line | VAD bleed / operator wait · tune `RELAY_VAD_*` or docs | Open |
| [UAT-003](#uat-003) | Agent + STT | “Compare payments and rate history” → payments only when STT garbles second clause | Clear script + agent parallel bundle routing · Phase 11 | Open |
| [UAT-004](#uat-004) | Demo | §12.1 steps 7–9 voice script (interrupt EMI → rate history) not completed in manual log | Phase 11 UAT | Open |
| [UAT-005](#uat-005) | Platform | ~~Silent TTS turn after barge-in~~ | Phase 7 / D-004-004 | **Closed** 2026-09-25 |
| [UAT-006](#uat-006) | Agent | Assistant leaks runtime/UI sync (“routed handler”, “can’t sync screen”); claims date update without field change | Mortgage agent guard rails + draft date routing · Phase 8 / 11 | **Verify** — patch landed 2026-09-25 |

### UAT-001

**EMI history** should prefer: `get_payments` / `get_rate_history` when case is open, or a concise “I only have current EMI **X** on file” — not a multi-paragraph generic definition.

### UAT-002

Event pattern: `SPEECH_STARTED` → immediate `INTERRUPTION_DETECTED`. Mitigation: pause before speaking while agent plays; reduce false barge-in (speaker bleed) in a later tuning pass.

### UAT-003

Use exact phrase **`Compare payments and rate history`**; confirm `ACTIVITY_*` + both tools in `relay_events`. Garbled STT is a demo risk — Phase 11 may add text fallback for critical demo steps.

### UAT-004

Tracked in [STATUS.md](./STATUS.md) Phase 7 manual UAT and Phase 11 exit.

### UAT-005

Fixed: `DeepgramTextToSpeechProvider` clears cancel at new `synthesize_stream`; see [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md).

### UAT-006

**User-facing guard rail:** Spoken and text replies must not mention Relay/runtime plumbing (e.g. “routed handler”, “can’t sync the UI”, “current UI state I can see”, `STATE_*`, tools pipeline). On a correction draft, date changes must go through **routed** recalculate + state sync — never LLM-only “I’m updating your screen now” while the effective-date field is unchanged.

**Verify (script row #11):**

1. Open draft for MORT-2931 (prepare correction flow).
2. Say or send **`Change it to March, not January`** (or **`03/01/2025`** after a clarify prompt).
3. **Pass:** effective date on screen matches; assistant describes the draft in plain language only.
4. **Fail:** any internal architecture leak in transcript/TTS, or spoken “updated” with field still **2025-01-01**.

**Implementation:** `examples/mortgage-servicing/agent/` — `system_prompt.txt`, `response_guardrails.py`, month/bare-date routing in `agent.py`. Tests: `runtime/tests/test_mortgage_agent_guardrails.py`. Design review: [GUARDRAILS_AND_SANITIZATION.md](./GUARDRAILS_AND_SANITIZATION.md).

---

## Phase 8 readiness

**Yes — you can start Phase 8.** Official dependency is **Phases 5–6** (signed off). Open items above are **agent/demo quality** and **Phase 11** narrative closure; they do not block `StateVersionEngine` / `STATE_CONFLICT` work.

Phase 8 does **not** require closing UAT-001–004 first; address those in parallel or before final POC sign-off (Phase 11). Close **UAT-006** after one post-rebuild pass of script row **#11**.
