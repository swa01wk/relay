"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createRelaySession,
  fetchHealth,
  registerPlaygroundSurfaces,
  submitForm,
  type RelayConnectionState,
  type RelayEventEnvelope,
  type UiSurface,
  type VoiceConnectionState,
} from "@sumukhj1219-wkt-org/relay-web-sdk";
import {
  CheckCircle2Icon,
  Loader2Icon,
  MicIcon,
  MicOffIcon,
  PhoneOffIcon,
  RotateCcwIcon,
  SendIcon,
  ShieldCheckIcon,
  SparklesIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { applyPresentUi, PlaygroundCanvas } from "@/components/playground-canvas";
import {
  CaseView,
  CorrectionDraftView,
  HomeView,
  RateHistoryView,
  SearchResultsView,
  WorkspaceHeader,
} from "@/components/workspace-views";
import {
  initialMortgageUiState,
  recalculateDraftForEffectiveDate,
  type MortgageUiState,
} from "@/lib/mortgage-ui-state";
import type { SendStateOptions } from "@sumukhj1219-wkt-org/relay-web-sdk";

const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080";
const projectId = process.env.NEXT_PUBLIC_PROJECT_ID ?? "proj-mortgage-poc";
const agentId = process.env.NEXT_PUBLIC_AGENT_ID ?? "agent-mortgage-ref";
// Experience Center: sessions come from this app's server, one data sandbox per visitor (src/lib/sandbox.ts).
const sandboxMode = ["1", "true", "yes"].includes((process.env.NEXT_PUBLIC_RELAY_SANDBOX ?? "").toLowerCase());

/** The session this app's server started for the visitor's sandbox. */
async function startSandboxSession(): Promise<{ sessionId: string; devToken: string }> {
  const res = await fetch("/api/assistant/session", { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error ?? `Couldn't start the demo session (status ${res.status})`);
  return { sessionId: body.sessionId, devToken: body.token };
}

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
  const [surfaces, setSurfaces] = useState<UiSurface[]>([]);
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
        registerPlaygroundSurfaces(session, (params) => {
          setSurfaces((current) => applyPresentUi(current, params));
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
    setSurfaces([]);
    publishUiState(initialMortgageUiState());
    sessionRef.current?.disconnect();
    let existing: { sessionId: string; devToken: string } | null = null;
    if (sandboxMode) {
      try {
        existing = await startSandboxSession();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setBusy(false);
        return;
      }
    }
    const session = createRelaySession({
      gatewayUrl,
      ...(existing ?? { projectId }),
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
      if (existing) {
        // A server-started session's SESSION_READY came in the server's response, not to us.
        appendMessage({ id: crypto.randomUUID(), role: "system", text: "Session ready." });
        publishUiState(uiStateRef.current);
      }
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

  const sendText = useCallback((text: string) => {
    if (!text.trim() || !sessionRef.current) return;
    setError(null);
    try {
      sessionRef.current.sendText(text.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "send failed");
    }
  }, []);

  const sendMessage = useCallback(() => {
    const text = draft.trim();
    if (!text) return;
    sendText(text);
    setDraft("");
  }, [draft, sendText]);

  const changeEffectiveDate = useCallback(
    (effectiveDate: string) => {
      const nextDraft = recalculateDraftForEffectiveDate(uiStateRef.current.correction_draft ?? {}, effectiveDate);
      setStateConflict(null);
      publishUiState({ ...uiStateRef.current, correction_draft: nextDraft }, { optimisticAdvance: true });
    },
    [publishUiState],
  );

  const resetDemo = useCallback(async () => {
    await fetch("/api/sandbox/reset", { method: "POST" }).catch(() => undefined);
    await connectSession();
  }, [connectSession]);

  const connected = connectionState === "ready";
  const voiceOn = voiceState === "connected" || voiceState === "connecting";
  const running = uiState.activities.filter((a) => a.status === "running");

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b bg-card/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground" aria-hidden="true">
            LS
          </span>
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-semibold">Loan Servicing Console</p>
            <p className="hidden text-xs text-muted-foreground sm:block">Example app · powered by Relay</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <ConnectionPill state={connectionState} />
            {sandboxMode && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                title="Your changes are private to you. Reset puts the demo data back."
                onClick={() => void resetDemo()}
              >
                <RotateCcwIcon className="size-4" /> <span className="hidden sm:inline">Reset demo</span>
              </Button>
            )}
            {(connected || messages.length > 0) && (
              <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={connectSession}>
                {connected ? "New conversation" : "Reconnect"}
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-[1400px] flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-w-0 flex-col gap-4">
          <section className="rounded-xl border bg-card shadow-sm" aria-label="Workspace">
            <div className="flex items-center gap-3 border-b px-4 py-2.5">
              <WorkspaceHeader state={uiState} />
              {running.length > 0 && (
                <span className="ml-auto flex items-center gap-1.5 text-xs text-primary">
                  <Loader2Icon className="size-3.5 animate-spin" /> {running[0].label ?? "Working"}
                </span>
              )}
            </div>
            <div key={uiState.screen} className="relay-screen-enter p-4 sm:p-5">
              {uiState.screen === "home" && <HomeView connected={connected} connecting={busy} onAsk={sendText} onConnect={() => void connectSession()} />}
              {uiState.screen === "search_results" && (
                <SearchResultsView state={uiState} onOpen={(id) => sendText(`Open ${id}`)} />
              )}
              {uiState.screen === "mortgage_case" && uiState.case_summary && <CaseView state={uiState} />}
              {uiState.screen === "correction_draft" && uiState.correction_draft && (
                <CorrectionDraftView state={uiState} onEffectiveDateChange={changeEffectiveDate} />
              )}
              {uiState.screen === "rate_history" && <RateHistoryView state={uiState} />}
            </div>
            {(commitVerified || stateConflict) && (
              <div className="space-y-2 border-t px-4 py-3">
                {commitVerified && (
                  <p className="flex items-center gap-2 rounded-md bg-success-soft px-3 py-2 text-sm text-success" data-testid="commit-verified-banner">
                    <CheckCircle2Icon className="size-4 shrink-0" /> {commitVerified}
                  </p>
                )}
                {stateConflict && (
                  <p className="flex items-center gap-2 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning" data-testid="state-conflict-banner">
                    <TriangleAlertIcon className="size-4 shrink-0" /> {stateConflict}
                  </p>
                )}
              </div>
            )}
          </section>

          <PlaygroundCanvas
            surfaces={surfaces}
            onSubmitForm={(form, values) => {
              if (sessionRef.current) submitForm(sessionRef.current, form, values);
            }}
            onRemove={(index) => setSurfaces((current) => current.filter((_, i) => i !== index))}
            onClear={() => setSurfaces([])}
          />

          <details className="rounded-xl border bg-card text-sm" data-testid="shared-state-panel">
            <summary className="cursor-pointer select-none px-4 py-2.5 text-xs font-medium text-muted-foreground">
              Developer details — connection, shared state
            </summary>
            <div className="space-y-3 border-t px-4 py-3">
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <Button type="button" size="sm" variant="outline" disabled={busy} onClick={checkHealth}>
                  Check /health
                </Button>
                {health && (
                  <span>
                    Gateway health: <strong className="text-foreground">{health}</strong>
                  </span>
                )}
                <span>
                  RP: <strong className="text-foreground">{connectionState}</strong> · Voice:{" "}
                  <strong className="text-foreground">{voiceState}</strong>
                </span>
                {sessionId && <code className="font-mono">{sessionId}</code>}
              </div>
              <pre className="max-h-60 overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                {JSON.stringify(uiState, null, 2)}
              </pre>
            </div>
          </details>
        </div>

        <aside
          className="flex min-h-[32rem] flex-col rounded-xl border bg-card shadow-sm lg:sticky lg:top-[4.5rem] lg:h-[calc(100dvh-5.5rem)]"
          aria-label="Assistant"
        >
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <SparklesIcon className="size-4 text-primary" aria-hidden="true" />
            <h2 className="text-sm font-semibold">Assistant</h2>
            {agentSpeaking && (
              <span className="flex items-center gap-1 text-xs text-primary">
                <span className="relay-pulse size-1.5 rounded-full bg-primary" /> speaking
              </span>
            )}
            {connected && (
              <div className="ml-auto flex items-center gap-1">
                {voiceOn && (
                  <Button
                    type="button"
                    size="icon"
                    variant={micMuted ? "destructive" : "ghost"}
                    disabled={voiceState !== "connected"}
                    onClick={toggleMute}
                    aria-label={micMuted ? "Unmute mic" : "Mute mic"}
                    title={micMuted ? "Unmute mic" : "Mute mic (use while the assistant speaks on open speakers)"}
                  >
                    {micMuted ? <MicOffIcon className="size-4" /> : <MicIcon className="size-4" />}
                  </Button>
                )}
                {voiceOn ? (
                  <Button type="button" size="sm" variant="outline" onClick={disconnectVoice}>
                    <PhoneOffIcon className="size-4" /> End voice
                  </Button>
                ) : (
                  <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={connectVoice}>
                    <MicIcon className="size-4" /> Start voice
                  </Button>
                )}
              </div>
            )}
          </div>

          {voiceState === "connected" && (
            <div className="flex items-center gap-3 border-b px-4 py-2 text-xs text-muted-foreground">
              <span className="shrink-0">Mic</span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" data-testid="mic-level-bar">
                <span
                  className="block h-full rounded-full bg-primary transition-[width] duration-100"
                  style={{ width: `${Math.min(100, Math.round(audioLevel * 250))}%` }}
                />
              </span>
              {audioLevel < 0.005 && <span className="shrink-0">silent — check mic permission</span>}
            </div>
          )}

          <div className="border-b px-4 py-2" data-testid="activity-panel">
            {uiState.activities.length === 0 ? (
              <p className="text-xs text-muted-foreground">No tools running.</p>
            ) : (
              <ul className="space-y-1.5">
                {uiState.activities.slice(-3).map((activity) => (
                  <li key={activity.activity_id} data-testid="activity-row" className="text-xs">
                    <div className="flex items-center gap-2">
                      {activity.status === "done" ? (
                        <CheckCircle2Icon className="size-3.5 text-success" />
                      ) : (
                        <Loader2Icon className="size-3.5 animate-spin text-primary" />
                      )}
                      <span className="flex-1 truncate font-medium">{activity.label ?? activity.activity_id}</span>
                      <span className="tabular text-muted-foreground">
                        {Math.round(activity.progress * 100)}% ({activity.status})
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
            {connectionState !== "ready" && messages.length === 0 && (
              <div className="m-auto flex max-w-xs flex-col items-center gap-3 text-center">
                <span className="grid size-11 place-items-center rounded-full bg-primary-soft text-primary">
                  <SparklesIcon className="size-5" />
                </span>
                <p className="text-sm font-medium">Your servicing assistant</p>
                <p className="text-xs text-muted-foreground">
                  Finds borrowers, explains payments and drafts corrections. Speak or type once connected.
                </p>
                <Button type="button" disabled={busy} onClick={connectSession}>
                  {busy && <Loader2Icon className="size-4 animate-spin" />}
                  Connect
                </Button>
              </div>
            )}
            {messages.map((m) => (
              <ChatBubble key={m.id} role={m.role} text={m.text} />
            ))}
            {liveTranscript.trim() && (
              <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm border border-dashed px-3 py-2 text-sm text-muted-foreground" data-testid="live-user-transcript">
                {liveTranscript}
              </div>
            )}
            {pendingApproval && (
              <div
                className="relay-panel-enter rounded-xl border border-warning/40 bg-warning-soft/60 p-4 text-sm"
                data-testid="approval-modal"
                role="group"
                aria-label="Approval required"
              >
                <p className="flex items-center gap-2 font-semibold">
                  <ShieldCheckIcon className="size-4 text-warning" /> Approval required
                </p>
                <p className="mt-1.5">{pendingApproval.summary}</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">{pendingApproval.toolName}</p>
                <div className="mt-3 flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    data-testid="approval-approve-btn"
                    onClick={() => sessionRef.current?.grantApproval(pendingApproval.approvalId)}
                  >
                    Approve &amp; commit
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    data-testid="approval-reject-btn"
                    onClick={() => sessionRef.current?.rejectApproval(pendingApproval.approvalId)}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            )}
          </div>

          {error && (
            <p className="mx-4 mb-2 flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-xs text-danger" role="alert">
              <TriangleAlertIcon className="mt-0.5 size-3.5 shrink-0" /> {error}
            </p>
          )}
          <form
            className="flex gap-2 border-t p-3"
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage();
            }}
          >
            <Input
              value={draft}
              placeholder='Try "Find Rajesh Sharma"'
              disabled={!connected}
              onChange={(e) => setDraft(e.target.value)}
              aria-label="Message the assistant"
            />
            <Button type="submit" size="icon" disabled={!connected || !draft.trim()} aria-label="Send" title="Send">
              <SendIcon className="size-4" />
            </Button>
          </form>
        </aside>
      </main>
    </div>
  );
}

function ConnectionPill({ state }: { state: RelayConnectionState }) {
  const meta = {
    ready: { label: "Assistant ready", dot: "bg-success", text: "text-success" },
    connecting: { label: "Connecting…", dot: "bg-warning relay-pulse", text: "text-warning" },
    error: { label: "Connection error", dot: "bg-danger", text: "text-danger" },
    disconnected: { label: "Offline", dot: "bg-muted-foreground", text: "text-muted-foreground" },
  }[state];
  return (
    <span
      className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium sm:inline-flex ${meta.text}`}
      data-testid="connection-state"
      data-state={state}
    >
      <span className={`size-1.5 rounded-full ${meta.dot}`} /> {meta.label}
    </span>
  );
}

function ChatBubble({ role, text }: { role: ChatLine["role"]; text: string }) {
  if (role === "system") {
    return (
      <p className="mx-auto text-center text-xs text-muted-foreground" data-testid="chat-message" data-chat-role={role}>
        {text}
      </p>
    );
  }
  const mine = role === "user";
  return (
    <div
      className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
        mine ? "ml-auto rounded-br-sm bg-primary text-primary-foreground" : "rounded-bl-sm bg-muted"
      }`}
      data-testid="chat-message"
      data-chat-role={role}
    >
      <span className="sr-only">{mine ? "You: " : "Assistant: "}</span>
      {text}
    </div>
  );
}
