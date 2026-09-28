"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createRelaySession,
  fetchHealth,
  type RelayConnectionState,
  type RelayEventEnvelope,
  type VoiceConnectionState,
} from "@relay/web-sdk";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  initialMortgageUiState,
  recalculateDraftForEffectiveDate,
  type MortgageUiState,
} from "@/lib/mortgage-ui-state";
import type { SendStateOptions } from "@relay/web-sdk";

const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080";
const projectId = process.env.NEXT_PUBLIC_PROJECT_ID ?? "proj-mortgage-poc";
const agentId = process.env.NEXT_PUBLIC_AGENT_ID ?? "agent-mortgage-ref";

type ChatLine = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
};

function findMortgageInResults(
  results: Array<Record<string, unknown>>,
  id: string,
): Record<string, unknown> | null {
  for (const customer of results) {
    const mortgages = (customer.mortgages as Array<Record<string, unknown>> | undefined) ?? [];
    for (const mortgage of mortgages) {
      if (String(mortgage.id) === id) {
        return { ...mortgage, customer_name: customer.name, customer_id: customer.id };
      }
    }
  }
  return null;
}

export default function HomePage() {
  const [health, setHealth] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<RelayConnectionState>("disconnected");
  const [voiceState, setVoiceState] = useState<VoiceConnectionState>("disconnected");
  const [micMuted, setMicMuted] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [audioLevel, setAudioLevel] = useState(0);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uiState, setUiState] = useState<MortgageUiState>(() => initialMortgageUiState());
  const [stateConflict, setStateConflict] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<{
    approvalId: string;
    summary: string;
    toolName: string;
  } | null>(null);
  const [commitVerified, setCommitVerified] = useState<string | null>(null);
  const sessionRef = useRef<ReturnType<typeof createRelaySession> | null>(null);
  const assistantBufferRef = useRef<{ id: string; text: string } | null>(null);
  const voiceStateRef = useRef<VoiceConnectionState>("disconnected");
  const uiStateRef = useRef(uiState);
  const unregisterActionsRef = useRef<Array<() => void>>([]);

  useEffect(() => {
    uiStateRef.current = uiState;
  }, [uiState]);

  useEffect(() => {
    voiceStateRef.current = voiceState;
  }, [voiceState]);

  const publishUiState = useCallback(
    (next: MortgageUiState, options?: SendStateOptions) => {
      setUiState(next);
      uiStateRef.current = next;
      try {
        sessionRef.current?.sendState(next as unknown as Record<string, unknown>, options);
      } catch {
        /* not connected yet */
      }
    },
    [],
  );

  useEffect(() => {
    return () => {
      unregisterActionsRef.current.forEach((off) => off());
      sessionRef.current?.disconnect();
    };
  }, []);

  const appendMessage = useCallback((line: ChatLine) => {
    setMessages((prev) => [...prev, line]);
  }, []);

  const wireActionHandlers = useCallback(
    (session: ReturnType<typeof createRelaySession>) => {
      unregisterActionsRef.current.forEach((off) => off());
      unregisterActionsRef.current = [
        session.registerAction("SHOW_SEARCH_RESULTS", (params) => {
          const customers = (params.customers as Array<Record<string, unknown>>) ?? [];
          const query = String(params.query ?? "");
          const next: MortgageUiState = {
            ...uiStateRef.current,
            screen: "search_results",
            workflow: "customer_search",
            search_query: query,
            search_results: customers,
          };
          publishUiState(next);
          session.sendEvent("ui.search_results", { query, count: customers.length });
        }),
        session.registerAction("OPEN_ENTITY", (params) => {
          const entityType = String(params.entity_type ?? "mortgage");
          const id = String(params.id ?? "");
          let caseSummary: Record<string, unknown> | null = null;
          if (entityType === "mortgage") {
            caseSummary =
              findMortgageInResults(uiStateRef.current.search_results, id) ?? {
                id,
                status: "active",
              };
          }
          const next: MortgageUiState = {
            ...uiStateRef.current,
            screen: "mortgage_case",
            workflow: "case_review",
            selected_entity: { type: entityType, id },
            case_summary: caseSummary,
          };
          publishUiState(next);
          session.sendEvent("ui.open_entity", { entity_type: entityType, id });
        }),
        session.registerAction("SHOW_CORRECTION_DRAFT", (params) => {
          const draft = (params.draft as Record<string, unknown>) ?? {};
          const mortgageId = String(params.mortgage_id ?? draft.mortgage_id ?? "");
          const next: MortgageUiState = {
            ...uiStateRef.current,
            screen: "correction_draft",
            workflow: "correction_draft",
            selected_entity: mortgageId
              ? { type: "mortgage", id: mortgageId }
              : uiStateRef.current.selected_entity,
            correction_draft: draft,
          };
          publishUiState(next);
          session.sendEvent("ui.correction_draft", { mortgage_id: mortgageId });
        }),
        session.registerAction("SHOW_RATE_HISTORY", (params) => {
          const rates = (params.rates as Array<Record<string, unknown>>) ?? [];
          const mortgageId = String(params.mortgage_id ?? "");
          const next: MortgageUiState = {
            ...uiStateRef.current,
            screen: "rate_history",
            workflow: "rate_investigation",
            rate_history: rates,
            selected_entity: mortgageId
              ? { type: "mortgage", id: mortgageId }
              : uiStateRef.current.selected_entity,
          };
          publishUiState(next);
          session.sendEvent("ui.rate_history", { mortgage_id: mortgageId, count: rates.length });
        }),
      ];
    },
    [publishUiState],
  );

  const checkHealth = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetchHealth(gatewayUrl);
      setHealth(res.status);
    } catch (e) {
      const raw = e instanceof Error ? e.message : "health failed";
      setError(
        raw.includes("fetch") || raw.includes("Failed")
          ? `Gateway not reachable at ${gatewayUrl}. Start Docker (docker compose -f infra/docker/docker-compose.yml up -d --build) and retry in a few seconds.`
          : raw,
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const connectSession = useCallback(async () => {
    setBusy(true);
    setError(null);
    setMessages([]);
    setLiveTranscript("");
    setStateConflict(null);
    setPendingApproval(null);
    setCommitVerified(null);
    publishUiState(initialMortgageUiState());
    sessionRef.current?.disconnect();
    const session = createRelaySession({
      gatewayUrl,
      projectId,
      agentId,
      transport: "small-webrtc",
    });
    sessionRef.current = session;
    wireActionHandlers(session);
    session.onConnectionState(setConnectionState);
    session.onVoiceState(setVoiceState);
    session.onAudioLevel(setAudioLevel);
    session.on("SESSION_READY", () => {
      setSessionId(session.sessionId);
      appendMessage({ id: crypto.randomUUID(), role: "system", text: "Session ready." });
      publishUiState(uiStateRef.current);
    });
    const showConflict = (expected: number, actual: number) => {
      if (typeof window !== "undefined") {
        const w = window as Window & { __relayConflictCount?: number };
        w.__relayConflictCount = (w.__relayConflictCount ?? 0) + 1;
      }
      setStateConflict(
        "An agent update was skipped because you changed the draft first — your date on screen was kept.",
      );
    };
    session.onStateConflict((info) => {
      showConflict(info.expectedVersion, info.actualVersion);
    });
    session.on("STATE_SNAPSHOT", (event: RelayEventEnvelope) => {
      const remote = event.payload.state;
      if (!remote || typeof remote !== "object") return;
      const incoming = remote as Partial<MortgageUiState>;
      setUiState((prev) => {
        const next: MortgageUiState = {
          ...prev,
          ...incoming,
          search_results: incoming.search_results ?? prev.search_results,
          case_summary: incoming.case_summary ?? prev.case_summary,
          rate_history: incoming.rate_history ?? prev.rate_history,
          correction_draft:
            incoming.correction_draft !== undefined
              ? incoming.correction_draft
              : prev.correction_draft,
          activities: incoming.activities ?? prev.activities,
        };
        uiStateRef.current = next;
        return next;
      });
    });
    session.on("SESSION_ERROR", (event: RelayEventEnvelope) => {
      const message = String(event.payload.message ?? "Session error");
      setError(message);
    });
    session.onApprovalRequested((event: RelayEventEnvelope) => {
      const approvalId = String(event.payload.approval_id ?? "");
      const summary = String(event.payload.summary ?? "Approve this correction?");
      const toolName = String(event.payload.tool_name ?? "");
      if (approvalId) {
        setPendingApproval({ approvalId, summary, toolName });
      }
    });
    session.on("COMMIT_VERIFIED", (event: RelayEventEnvelope) => {
      const verified = Boolean(event.payload.verified);
      const commitId = String(event.payload.commit_id ?? "");
      setPendingApproval(null);
      setCommitVerified(
        verified ? `Correction committed and verified (${commitId}).` : "Commit verification failed.",
      );
    });
    session.on("APPROVAL_REJECTED", () => {
      setPendingApproval(null);
      appendMessage({
        id: crypto.randomUUID(),
        role: "system",
        text: "Approval rejected — draft unchanged.",
      });
    });
    session.on("TRANSCRIPT_DELTA", (event: RelayEventEnvelope) => {
      setLiveTranscript(String(event.payload.text ?? ""));
    });
    session.on("TRANSCRIPT_FINAL", (event: RelayEventEnvelope) => {
      const text = String(event.payload.text ?? "");
      setLiveTranscript("");
      appendMessage({ id: String(event.metadata.event_id ?? crypto.randomUUID()), role: "user", text });
    });
    const syncAssistantMessage = (id: string, text: string) => {
      setMessages((prev) => {
        const existing = prev.find((m) => m.id === id);
        if (existing) {
          return prev.map((m) => (m.id === id ? { ...m, text } : m));
        }
        return [...prev, { id, role: "assistant", text }];
      });
    };

    session.on("RESPONSE_STARTED", () => {
      const id = crypto.randomUUID();
      assistantBufferRef.current = { id, text: "" };
      if (voiceStateRef.current === "connected") {
        syncAssistantMessage(id, "");
      }
    });
    session.on("RESPONSE_DELTA", (event: RelayEventEnvelope) => {
      const chunk = String(event.payload.text ?? "");
      const buf = assistantBufferRef.current;
      if (!buf) return;
      buf.text += chunk;
      if (voiceStateRef.current !== "connected") {
        syncAssistantMessage(buf.id, buf.text);
      }
    });
    session.on("SPEECH_PROGRESS", (event: RelayEventEnvelope) => {
      const buf = assistantBufferRef.current;
      if (!buf || voiceStateRef.current !== "connected") return;
      const heard = String(event.payload.heard_text ?? "");
      if (heard) {
        syncAssistantMessage(buf.id, heard);
      }
    });
    session.on("RESPONSE_INTERRUPTED", (event: RelayEventEnvelope) => {
      const buf = assistantBufferRef.current;
      if (!buf) return;
      const heard = String(event.payload.heard_text ?? "");
      if (heard) {
        syncAssistantMessage(buf.id, heard);
      }
    });
    session.on("agent_activity", (event: RelayEventEnvelope) => {
      setAgentSpeaking(Boolean(event.payload.speaking));
    });
    session.on("SPEECH_STARTED", () => setAgentSpeaking(true));
    session.on("SPEECH_STOPPED", () => setAgentSpeaking(false));
    session.on("RESPONSE_COMPLETED", (event: RelayEventEnvelope) => {
      const text = String(event.payload.text ?? "");
      const buf = assistantBufferRef.current;
      if (buf) {
        syncAssistantMessage(buf.id, text || buf.text);
      }
      assistantBufferRef.current = null;
    });
    session.on("ACTION_FAILED", (event: RelayEventEnvelope) => {
      appendMessage({
        id: crypto.randomUUID(),
        role: "system",
        text: `Action failed (${event.payload.action}): ${event.payload.reason}`,
      });
    });
    const upsertActivity = (
      activityId: string,
      patch: Partial<MortgageUiState["activities"][number]>,
    ) => {
      setUiState((prev) => {
        const existing = prev.activities.find((a) => a.activity_id === activityId);
        const activities = existing
          ? prev.activities.map((a) =>
              a.activity_id === activityId ? { ...a, ...patch } : a,
            )
          : [
              ...prev.activities,
              {
                activity_id: activityId,
                label: patch.label,
                progress: patch.progress ?? 0,
                status: patch.status ?? "running",
              },
            ];
        const next = { ...prev, activities };
        uiStateRef.current = next;
        try {
          session.sendState(next as unknown as Record<string, unknown>, { optimisticAdvance: true });
        } catch {
          /* ignore */
        }
        return next;
      });
    };
    session.on("ACTIVITY_STARTED", (event: RelayEventEnvelope) => {
      const activityId = String(event.payload.activity_id ?? "");
      if (!activityId) return;
      upsertActivity(activityId, {
        label: String(event.payload.label ?? "Working"),
        progress: 0,
        status: "running",
      });
    });
    session.on("ACTIVITY_PROGRESS", (event: RelayEventEnvelope) => {
      const activityId = String(event.payload.activity_id ?? "");
      if (!activityId) return;
      upsertActivity(activityId, {
        progress: Number(event.payload.progress ?? 0),
        status: "running",
      });
    });
    session.on("ACTIVITY_COMPLETED", (event: RelayEventEnvelope) => {
      const activityId = String(event.payload.activity_id ?? "");
      if (!activityId) return;
      upsertActivity(activityId, { progress: 1, status: "done" });
    });
    try {
      await session.connect();
      setSessionId(session.sessionId);
    } catch (e) {
      const raw = e instanceof Error ? e.message : "session failed";
      setError(
        raw.includes("fetch") || raw.includes("websocket") || raw.includes("Failed")
          ? `Could not connect to ${gatewayUrl}. Ensure the gateway container is up (Check /health).`
          : raw,
      );
    } finally {
      setBusy(false);
    }
  }, [appendMessage, publishUiState, wireActionHandlers]);

  const connectVoice = useCallback(async () => {
    if (!sessionRef.current) return;
    setBusy(true);
    setError(null);
    try {
      await sessionRef.current.connectVoice();
    } catch (e) {
      setError(e instanceof Error ? e.message : "voice connect failed");
    } finally {
      setBusy(false);
    }
  }, []);

  const disconnectVoice = useCallback(async () => {
    await sessionRef.current?.disconnectVoice();
    setAudioLevel(0);
    setMicMuted(false);
  }, []);

  const toggleMute = useCallback(() => {
    const next = !micMuted;
    setMicMuted(next);
    sessionRef.current?.setMicMuted(next);
  }, [micMuted]);

  const sendMessage = useCallback(() => {
    const text = draft.trim();
    if (!text || !sessionRef.current) return;
    setError(null);
    try {
      sessionRef.current.sendText(text);
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "send failed");
    }
  }, [draft]);

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-8">
      <Card>
        <CardHeader>
          <CardTitle>Mortgage servicing — tools &amp; investigations</CardTitle>
          <CardDescription>
            Phase 9 — draft → approval → commit → verify (try: prepare correction draft, then
            &quot;Submit for approval&quot; and use the approval dialog).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={busy} onClick={checkHealth}>
              Check /health
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={connectSession}>
              Connect
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={busy || connectionState !== "ready"}
              onClick={connectVoice}
            >
              Connect voice
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={voiceState === "disconnected"}
              onClick={disconnectVoice}
            >
              Disconnect voice
            </Button>
            <Button
              type="button"
              variant={micMuted ? "destructive" : "outline"}
              disabled={voiceState !== "connected"}
              onClick={toggleMute}
            >
              {micMuted ? "Unmute mic" : "Mute mic"}
            </Button>
          </div>
          {health && (
            <p className="text-sm">
              Gateway health: <strong>{health}</strong>
            </p>
          )}
          {voiceState === "connected" && (
            <div className="space-y-1 text-sm text-muted-foreground">
              <p>
                Voice is on — speak after the mic meter moves, or use Send for spoken text replies.
                On open speakers, use <strong>Mute mic</strong> while the agent is speaking to avoid
                echo and false interrupts.
              </p>
              <p className="text-xs">
                Mic level:{" "}
                <span data-testid="mic-level-bar" className="inline-block min-w-[8rem]">
                  {"█".repeat(Math.min(20, Math.round(audioLevel * 40))) ||
                    (audioLevel > 0.005 ? "▪" : "—")}
                </span>{" "}
                {audioLevel < 0.005 ? "(silent — check macOS mic permission for Chrome)" : ""}
              </p>
            </div>
          )}
          <p className="text-sm">
            RP: <strong>{connectionState}</strong> · Voice: <strong>{voiceState}</strong>
            {agentSpeaking && (
              <>
                {" "}
                · <strong className="text-primary">Agent speaking</strong>
              </>
            )}
            {sessionId && (
              <>
                {" "}
                · session <code className="text-xs">{sessionId}</code>
              </>
            )}
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="relay-panel-enter rounded-md border p-3 transition-shadow duration-300 hover:shadow-sm">
              <p className="text-xs font-medium text-muted-foreground">Application view</p>
              <div key={uiState.screen} className="relay-screen-enter">
              {uiState.screen === "home" && (
                <p className="mt-2 text-sm text-muted-foreground">
                  Connect and ask the agent to find Rajesh Sharma or open MORT-2931.
                </p>
              )}
              {uiState.screen === "search_results" && (
                <div className="mt-2 space-y-2" data-testid="search-results-view">
                  <p className="text-sm font-medium">Search: {uiState.search_query}</p>
                  <ul className="list-disc pl-5 text-sm">
                    {uiState.search_results.map((c) => (
                      <li key={String(c.id)} data-testid="search-result-row">
                        {String(c.name)} ({String(c.id)})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {uiState.screen === "mortgage_case" && uiState.case_summary && (
                <div className="mt-2 space-y-1 text-sm" data-testid="mortgage-case-view">
                  <p className="font-medium">Case {String(uiState.case_summary.id)}</p>
                  <p>{String(uiState.case_summary.customer_name ?? "")}</p>
                  <p>{String(uiState.case_summary.property ?? "")}</p>
                  <p>Status: {String(uiState.case_summary.status ?? "unknown")}</p>
                  <p data-testid="case-current-rate">
                    Rate: {Number(uiState.case_summary.current_rate ?? 0).toFixed(3)}%
                  </p>
                  <p data-testid="case-current-emi">
                    EMI: ${Number(uiState.case_summary.emi ?? 0).toFixed(2)}
                  </p>
                </div>
              )}
              {uiState.screen === "correction_draft" && uiState.correction_draft && (
                <div className="mt-2 space-y-2 text-sm" data-testid="correction-draft-view">
                  <p className="font-medium">
                    Draft correction — {String(uiState.correction_draft.mortgage_id ?? "")}
                  </p>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-muted-foreground">Effective date</span>
                    <Input
                      data-testid="correction-effective-date"
                      value={String(uiState.correction_draft.effective_date ?? "")}
                      onChange={(e) => {
                        const effectiveDate = e.target.value;
                        const draft = recalculateDraftForEffectiveDate(
                          uiStateRef.current.correction_draft ?? {},
                          effectiveDate,
                        );
                        const next: MortgageUiState = {
                          ...uiStateRef.current,
                          correction_draft: draft,
                        };
                        setStateConflict(null);
                        publishUiState(next, { optimisticAdvance: true });
                      }}
                    />
                  </label>
                  <p data-testid="correction-projected-emi">
                    Projected EMI: ${Number(uiState.correction_draft.projected_emi ?? 0).toFixed(2)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Delta ${Number(uiState.correction_draft.estimated_emi_delta ?? 0).toFixed(2)} vs
                    current ${Number(uiState.correction_draft.current_emi ?? 0).toFixed(2)}
                  </p>
                  <p className="text-xs" data-testid="draft-status">
                    Status: {String(uiState.correction_draft.status ?? "draft")}
                  </p>
                </div>
              )}
              {uiState.screen === "rate_history" && (
                <div className="mt-2 space-y-2" data-testid="rate-history-view">
                  <p className="text-sm font-medium">Rate history</p>
                  <ul className="list-disc pl-5 text-sm">
                    {uiState.rate_history.map((row, idx) => (
                      <li key={`${String(row.effective_date)}-${idx}`}>
                        {String(row.effective_date)}: {String(row.rate)}% ({String(row.reason ?? "")})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              </div>
            </div>
            <div
              className="relay-panel-enter rounded-md border p-3 transition-shadow duration-300 hover:shadow-sm"
              data-testid="activity-panel"
            >
              <p className="text-xs font-medium text-muted-foreground">Agent activity (RP)</p>
              {uiState.activities.length === 0 ? (
                <p className="mt-2 text-sm text-muted-foreground">No in-flight tool activity.</p>
              ) : (
                <ul className="mt-2 space-y-2 text-sm">
                  {uiState.activities.map((activity) => (
                    <li key={activity.activity_id} data-testid="activity-row">
                      <span className="font-medium">{activity.label ?? activity.activity_id}</span>{" "}
                      — {Math.round(activity.progress * 100)}% ({activity.status})
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div
              className="relay-panel-enter rounded-md border p-3 transition-shadow duration-300 hover:shadow-sm md:col-span-2"
              data-testid="shared-state-panel"
            >
              <p className="text-xs font-medium text-muted-foreground">Shared state (RP)</p>
              <pre className="mt-2 max-h-40 overflow-auto text-xs">{JSON.stringify(uiState, null, 2)}</pre>
            </div>
          </div>
          <div className="flex max-h-60 flex-col gap-2 overflow-y-auto rounded-md border p-3">
            {messages.map((m) => (
              <div
                key={m.id}
                className="text-sm"
                data-testid="chat-message"
                data-chat-role={m.role}
              >
                <span className="font-medium capitalize">{m.role}:</span> {m.text}
              </div>
            ))}
            {liveTranscript.trim() && (
              <div className="text-sm text-muted-foreground" data-testid="live-user-transcript">
                <span className="font-medium">User (speaking):</span> {liveTranscript}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <Input
              value={draft}
              placeholder='Try "Find Rajesh Sharma"'
              disabled={connectionState !== "ready"}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendMessage();
              }}
            />
            <Button type="button" disabled={connectionState !== "ready" || !draft.trim()} onClick={sendMessage}>
              Send
            </Button>
          </div>
          {pendingApproval && (
            <div
              className="rounded-md border border-blue-200 bg-blue-50 p-4 text-sm"
              data-testid="approval-modal"
              role="dialog"
              aria-label="Approval required"
            >
              <p className="font-medium">Approval required</p>
              <p className="mt-1 text-muted-foreground">{pendingApproval.summary}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Tool: {pendingApproval.toolName}
              </p>
              <div className="mt-3 flex gap-2">
                <Button
                  type="button"
                  data-testid="approval-approve-btn"
                  onClick={() => sessionRef.current?.grantApproval(pendingApproval.approvalId)}
                >
                  Approve &amp; commit
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  data-testid="approval-reject-btn"
                  onClick={() => sessionRef.current?.rejectApproval(pendingApproval.approvalId)}
                >
                  Reject
                </Button>
              </div>
            </div>
          )}
          {commitVerified && (
            <p className="text-sm text-green-800" data-testid="commit-verified-banner">
              {commitVerified}
            </p>
          )}
          {stateConflict && (
            <p className="text-sm text-amber-700" data-testid="state-conflict-banner">
              {stateConflict}
            </p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </CardContent>
      </Card>
    </main>
  );
}
