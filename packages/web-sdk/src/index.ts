/** Relay Web SDK — text control plane + optional SmallWebRTC media (Phase 2). */

import {
  attachSmallWebRtcMedia,
  type SmallWebRtcSession,
  type VoiceConnectionState,
} from "./webrtc-media";

export type RelayConnectionState = "disconnected" | "connecting" | "ready" | "error";

export type RelayTransportMode = "text-only" | "small-webrtc";

export type RelayEventEnvelope = {
  type: string;
  metadata: Record<string, unknown>;
  payload: Record<string, unknown>;
};

export type DevSessionResult = {
  sessionId: string;
  devToken: string;
  tokenExpiresAt: string;
  events: RelayEventEnvelope[];
};

export type RelaySessionOptions = {
  gatewayUrl: string;
  projectId: string;
  agentId: string;
  /** Use existing dev session instead of POST /dev/sessions */
  sessionId?: string;
  devToken?: string;
  /** Phase 2: attach SmallWebRTC after RP session is ready */
  transport?: RelayTransportMode;
  iceServers?: RTCIceServer[];
};

export type ActionHandler = (
  params: Record<string, unknown>,
  ctx: { actionId: string; name: string },
) => void | Promise<void>;

export type SendStateOptions = {
  /** Version the client read before this edit (defaults to last server version). */
  basedOnVersion?: number;
  /** §10.3 — bump local version immediately on human edit before server ack. */
  optimisticAdvance?: boolean;
};

export type StateConflictInfo = {
  expectedVersion: number;
  actualVersion: number;
  patch?: unknown[];
};

export type RelaySession = {
  connectionState: RelayConnectionState;
  voiceState: VoiceConnectionState;
  sessionId: string | null;
  /** Monotonic shared state version (server ack + optimistic client edits). */
  stateVersion: number;
  connect: () => Promise<void>;
  disconnect: () => void;
  connectVoice: () => Promise<void>;
  disconnectVoice: () => Promise<void>;
  setMicMuted: (muted: boolean) => void;
  cancelVoiceUtterance: () => void;
  sendText: (text: string) => void;
  registerAction: (name: string, handler: ActionHandler) => () => void;
  sendState: (state: Record<string, unknown>, options?: SendStateOptions) => void;
  onStateConflict: (handler: (info: StateConflictInfo) => void) => () => void;
  sendEvent: (name: string, payload?: Record<string, unknown>) => void;
  /** Phase 9 — HITL approval UI hook (alias for `on("APPROVAL_REQUESTED")`). */
  onApprovalRequested: (handler: (event: RelayEventEnvelope) => void) => () => void;
  grantApproval: (approvalId: string, authProof?: string) => void;
  rejectApproval: (approvalId: string) => void;
  on: (eventType: string, handler: (event: RelayEventEnvelope) => void) => () => void;
  onConnectionState: (handler: (state: RelayConnectionState) => void) => () => void;
  onVoiceState: (handler: (state: VoiceConnectionState) => void) => () => void;
  onAudioLevel: (handler: (level: number) => void) => () => void;
};

export type { VoiceConnectionState };

export async function fetchHealth(gatewayUrl: string): Promise<{ status: string }> {
  const res = await fetch(`${gatewayUrl.replace(/\/$/, "")}/health`);
  if (!res.ok) throw new Error(`health check failed: ${res.status}`);
  return res.json() as Promise<{ status: string }>;
}

export async function createDevSession(
  gatewayUrl: string,
  params: { projectId: string; agentId: string },
): Promise<DevSessionResult> {
  const res = await fetch(`${gatewayUrl.replace(/\/$/, "")}/dev/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: params.projectId,
      agent_id: params.agentId,
    }),
  });
  if (!res.ok) throw new Error(`dev session failed: ${res.status}`);
  const body = (await res.json()) as {
    session_id: string;
    dev_token: string;
    token_expires_at: string;
    events: DevSessionResult["events"];
  };
  return {
    sessionId: body.session_id,
    devToken: body.dev_token,
    tokenExpiresAt: body.token_expires_at,
    events: body.events,
  };
}

export function createRelaySession(options: RelaySessionOptions): RelaySession {
  const baseUrl = options.gatewayUrl.replace(/\/$/, "");
  const transportMode: RelayTransportMode = options.transport ?? "text-only";
  let connectionState: RelayConnectionState = "disconnected";
  let voiceState: VoiceConnectionState = "disconnected";
  let sessionId: string | null = options.sessionId ?? null;
  let devToken: string | null = options.devToken ?? null;
  let socket: WebSocket | null = null;
  let voice: SmallWebRtcSession | null = null;
  const typeHandlers = new Map<string, Set<(event: RelayEventEnvelope) => void>>();
  const actionHandlers = new Map<string, ActionHandler>();
  const stateHandlers = new Set<(state: RelayConnectionState) => void>();
  const voiceStateHandlers = new Set<(state: VoiceConnectionState) => void>();
  const audioLevelHandlers = new Set<(level: number) => void>();
  const stateConflictHandlers = new Set<(info: StateConflictInfo) => void>();
  let stateVersion = 0;

  const setState = (next: RelayConnectionState) => {
    connectionState = next;
    for (const handler of stateHandlers) handler(next);
  };

  const setVoiceState = (next: VoiceConnectionState) => {
    voiceState = next;
    for (const handler of voiceStateHandlers) handler(next);
  };

  let agentSpeaking = false;

  const emitAgentActivity = (speaking: boolean) => {
    if (agentSpeaking === speaking) return;
    agentSpeaking = speaking;
    const handlers = typeHandlers.get("agent_activity");
    if (handlers) {
      const envelope: RelayEventEnvelope = {
        type: "agent_activity",
        metadata: { session_id: sessionId ?? undefined },
        payload: { speaking },
      };
      for (const handler of handlers) handler(envelope);
    }
  };

  const sendJson = (body: Record<string, unknown>) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      throw new Error("not connected");
    }
    socket.send(JSON.stringify(body));
  };

  const handleActionRequested = async (event: RelayEventEnvelope) => {
    const name = String(event.payload.action ?? "");
    const actionId = String(event.payload.action_id ?? "");
    const params = (event.payload.params ?? {}) as Record<string, unknown>;
    const handler = actionHandlers.get(name);
    if (!handler) {
      sendJson({
        type: "ACTION_FAILED",
        action: name,
        action_id: actionId,
        reason: "no_handler_registered",
      });
      return;
    }
    try {
      await handler(params, { actionId, name });
      sendJson({
        type: "ACTION_APPLIED",
        action: name,
        action_id: actionId,
        result: { ok: true },
      });
    } catch (err) {
      sendJson({
        type: "ACTION_FAILED",
        action: name,
        action_id: actionId,
        reason: err instanceof Error ? err.message : "action_handler_failed",
      });
    }
  };

  const noteServerStateVersion = (version: unknown) => {
    const parsed = Number(version);
    if (Number.isFinite(parsed) && parsed >= 0) {
      stateVersion = Math.max(stateVersion, parsed);
    }
  };

  const emitStateConflict = (info: StateConflictInfo) => {
    for (const handler of stateConflictHandlers) handler(info);
    const handlers = typeHandlers.get("state_conflict");
    if (handlers) {
      const envelope: RelayEventEnvelope = {
        type: "state_conflict",
        metadata: { session_id: sessionId ?? undefined },
        payload: {
          expected_version: info.expectedVersion,
          actual_version: info.actualVersion,
          patch: info.patch,
        },
      };
      for (const handler of handlers) handler(envelope);
    }
  };

  const emit = (event: RelayEventEnvelope) => {
    if (event.type === "STATE_VERSION_ADVANCED") {
      noteServerStateVersion(event.payload.state_version);
    }
    if (event.type === "STATE_SNAPSHOT") {
      noteServerStateVersion(event.payload.state_version);
    }
    if (event.type === "STATE_CONFLICT") {
      emitStateConflict({
        expectedVersion: Number(event.payload.expected_version ?? 0),
        actualVersion: Number(event.payload.actual_version ?? 0),
        patch: event.payload.patch as unknown[] | undefined,
      });
    }
    const handlers = typeHandlers.get(event.type);
    if (handlers) {
      for (const handler of handlers) handler(event);
    }
    if (event.type === "ACTION_REQUESTED") {
      void handleActionRequested(event);
    }
    if (event.type === "APPROVAL_REQUESTED") {
      const approvalHandlers = typeHandlers.get("approval_requested");
      if (approvalHandlers) {
        for (const handler of approvalHandlers) handler(event);
      }
    }
    if (event.type === "TRANSCRIPT_FINAL") {
      const transcriptHandlers = typeHandlers.get("transcript");
      if (transcriptHandlers) {
        for (const handler of transcriptHandlers) handler(event);
      }
    }
    if (event.type === "SPEECH_STARTED") {
      emitAgentActivity(true);
    }
    if (event.type === "SPEECH_STOPPED") {
      emitAgentActivity(false);
    }
  };

  const ensureVoice = () => {
    if (transportMode !== "small-webrtc") {
      throw new Error('voice requires transport: "small-webrtc"');
    }
    if (!sessionId || !devToken) {
      throw new Error("connect RP session before voice");
    }
    if (!voice) {
      voice = attachSmallWebRtcMedia({
        gatewayUrl: baseUrl,
        sessionId,
        devToken,
        iceServers: options.iceServers,
      });
      voice.onConnectionState(setVoiceState);
      voice.onAudioLevel((level) => {
        for (const handler of audioLevelHandlers) handler(level);
      });
    }
    return voice;
  };

  const on = (eventType: string, handler: (event: RelayEventEnvelope) => void) => {
    if (!typeHandlers.has(eventType)) typeHandlers.set(eventType, new Set());
    typeHandlers.get(eventType)!.add(handler);
    return () => typeHandlers.get(eventType)?.delete(handler);
  };

  const onConnectionState = (handler: (state: RelayConnectionState) => void) => {
    stateHandlers.add(handler);
    handler(connectionState);
    return () => stateHandlers.delete(handler);
  };

  const onVoiceState = (handler: (state: VoiceConnectionState) => void) => {
    voiceStateHandlers.add(handler);
    handler(voiceState);
    return () => voiceStateHandlers.delete(handler);
  };

  const onAudioLevel = (handler: (level: number) => void) => {
    audioLevelHandlers.add(handler);
    return () => audioLevelHandlers.delete(handler);
  };

  const connect = async () => {
    setState("connecting");
    try {
      if (!sessionId || !devToken) {
        const created = await createDevSession(baseUrl, {
          projectId: options.projectId,
          agentId: options.agentId,
        });
        sessionId = created.sessionId;
        devToken = created.devToken;
        for (const event of created.events) emit(event);
      }
      const wsUrl = baseUrl.replace(/^http/, "ws");
      socket = new WebSocket(
        `${wsUrl}/ws/sessions/${sessionId}?token=${encodeURIComponent(devToken!)}`,
      );
      await new Promise<void>((resolve, reject) => {
        if (!socket) return reject(new Error("socket missing"));
        socket.onopen = () => resolve();
        socket.onerror = () => reject(new Error("websocket error"));
      });
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(String(message.data)) as RelayEventEnvelope;
          emit(event);
          if (event.type === "SESSION_READY") setState("ready");
        } catch {
          /* ignore malformed */
        }
      };
      socket.onclose = () => {
        setState("disconnected");
        void voice?.disconnect();
      };
      setState("ready");
    } catch (e) {
      setState("error");
      throw e;
    }
  };

  const disconnect = () => {
    void voice?.disconnect();
    voice = null;
    socket?.close();
    socket = null;
    setState("disconnected");
    setVoiceState("disconnected");
  };

  const connectVoice = async () => {
    const media = ensureVoice();
    try {
      await media.connect();
    } catch (e) {
      setVoiceState("failed");
      throw e;
    }
  };

  const disconnectVoice = async () => {
    await voice?.disconnect();
    setVoiceState("disconnected");
  };

  /** Mute local mic only — does not cancel an in-flight turn (use `cancelVoiceUtterance`). */
  const setMicMuted = (muted: boolean) => {
    voice?.setMicMuted(muted);
  };

  const cancelVoiceUtterance = () => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "VOICE_CANCEL" }));
  };

  const sendText = (text: string) => {
    sendJson({ type: "USER_TEXT", text });
  };

  const registerAction = (name: string, handler: ActionHandler) => {
    actionHandlers.set(name, handler);
    return () => actionHandlers.delete(name);
  };

  const sendState = (state: Record<string, unknown>, options?: SendStateOptions) => {
    const basedOn = options?.basedOnVersion ?? stateVersion;
    if (options?.optimisticAdvance) {
      stateVersion += 1;
    }
    sendJson({
      type: "STATE_SNAPSHOT",
      state,
      based_on_version: basedOn,
      client_state_version: stateVersion,
    });
  };

  const onStateConflict = (handler: (info: StateConflictInfo) => void) => {
    stateConflictHandlers.add(handler);
    return () => stateConflictHandlers.delete(handler);
  };

  const sendEvent = (name: string, payload: Record<string, unknown> = {}) => {
    sendJson({ type: "APP_EVENT", name, payload });
  };

  const onApprovalRequested = (handler: (event: RelayEventEnvelope) => void) =>
    on("approval_requested", handler);

  const grantApproval = (approvalId: string, authProof = "dev-approver") => {
    sendEvent("approval.grant", { approval_id: approvalId, auth_proof: authProof });
  };

  const rejectApproval = (approvalId: string) => {
    sendEvent("approval.reject", { approval_id: approvalId });
  };

  return {
    get connectionState() {
      return connectionState;
    },
    get voiceState() {
      return voiceState;
    },
    get sessionId() {
      return sessionId;
    },
    get stateVersion() {
      return stateVersion;
    },
    connect,
    disconnect,
    connectVoice,
    disconnectVoice,
    setMicMuted,
    cancelVoiceUtterance,
    sendText,
    registerAction,
    sendState,
    onStateConflict,
    sendEvent,
    onApprovalRequested,
    grantApproval,
    rejectApproval,
    on,
    onConnectionState,
    onVoiceState,
    onAudioLevel,
  };
}
