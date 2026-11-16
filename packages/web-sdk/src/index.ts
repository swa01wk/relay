/** Relay Web SDK — text control plane + optional SmallWebRTC media (Phase 2). */

import {
  attachSmallWebRtcMedia,
  type SmallWebRtcSession,
  type VoiceConnectionState,
} from "./webrtc-media.js";

export {
  FILL_FORM_ACTION,
  FORM_SUBMIT_EVENT,
  PRESENT_UI_ACTION,
  SHOW_TABLE_ACTION,
  normalizeChartSurface,
  normalizePresentUiParams,
  normalizeTableSurface,
  normalizeUiSurface,
  registerFormFill,
  registerPlaygroundSurfaces,
  submitForm,
  surfaceToCsv,
} from "./ui-surfaces.js";
export { NAVIGATE_ACTION, registerAutoNavigation } from "./navigation.js";
export type { AutoNavigationOptions, NavigationPage } from "./navigation.js";
export { PAGE_FORM_ACTION_PREFIX, registerPageForms } from "./page-forms.js";
export type { PageFormsOptions } from "./page-forms.js";
export type {
  PresentUiParams,
  UiCardsSurface,
  UiChartSurface,
  UiChartType,
  UiComparisonSurface,
  UiFormField,
  UiFormFieldType,
  UiFormFill,
  UiFormSurface,
  UiMarkdownSurface,
  UiKeyValueSurface,
  UiNoticeSurface,
  UiSurface,
  UiTableColumn,
  UiTableSurface,
} from "./ui-surfaces.js";

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
  /**
   * Project API key. In a browser use the project's publishable key (`rpk_…`, from
   * `relay keys create --kind publishable`); never ship a secret key (`rsk_…`) to a browser.
   * The key decides the project, so `projectId` is not needed.
   */
  apiKey?: string;
  /** Only for local development without a key (gateway started with RELAY_DEV_SESSIONS=1). */
  projectId?: string;
  agentId: string;
  /** Use an existing session instead of creating one */
  sessionId?: string;
  devToken?: string;
  /** Phase 2: attach SmallWebRTC after RP session is ready */
  transport?: RelayTransportMode;
  /**
   * STUN/TURN servers for voice. Leave unset to use the ones the gateway hands out for the session
   * (including TURN, which relays audio through strict firewalls).
   */
  iceServers?: RTCIceServer[];
};

/** Return an object to report it back to the agent (e.g. `{ rows_shown: 23 }`). Throw to fail. */
export type ActionHandler = (
  params: Record<string, unknown>,
  ctx: { actionId: string; name: string },
) => void | Record<string, unknown> | Promise<void | Record<string, unknown>>;

/** Describes an action so the agent can call it to change what the user sees. */
export type ActionSpec = {
  /** What the action does, written for the AI (e.g. "Filter the orders table on the dashboard"). */
  description: string;
  /** JSON Schema for the params: `{ type: "object", properties: {...}, required?: [...] }`. */
  parameters?: Record<string, unknown>;
};

/** APP_EVENT that advertises spec'd actions to the agent. */
export const CLIENT_CAPABILITIES_EVENT = "ui.capabilities";

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
  /** With `spec`, the agent is told about the action and may call it ("change the screen"). */
  registerAction: (name: string, handler: ActionHandler, spec?: ActionSpec) => () => void;
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

/** Which of your app's users a session is for. Sent to your tools service on every call. */
export type RelayEndUser = {
  /** Your own id for the signed-in user. */
  id: string;
  /** Optional facts your tools need (role, organisation, …): strings, numbers or booleans. */
  attributes?: Record<string, string | number | boolean>;
};

/**
 * Start a session in the project the API key belongs to (`POST /v1/sessions`).
 *
 * `user` may only be set with a **secret** key, i.e. from your server after it has checked who
 * is signed in; hand the returned `sessionId` and `devToken` to the browser
 * (`createRelaySession({ sessionId, devToken, … })`).
 */
export async function createSession(
  gatewayUrl: string,
  params: { apiKey: string; agentId: string; user?: RelayEndUser },
): Promise<DevSessionResult> {
  const res = await fetch(`${gatewayUrl.replace(/\/$/, "")}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${params.apiKey}` },
    body: JSON.stringify({ agent_id: params.agentId, ...(params.user ? { user: params.user } : {}) }),
  });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((body: { detail?: unknown }) => (typeof body.detail === "string" ? body.detail : ""))
      .catch(() => "");
    throw new Error(`session failed: ${res.status}${detail ? ` — ${detail}` : ""}`);
  }
  const body = (await res.json()) as {
    session_id: string;
    token: string;
    token_expires_at: string;
    events: DevSessionResult["events"];
  };
  return {
    sessionId: body.session_id,
    devToken: body.token,
    tokenExpiresAt: body.token_expires_at,
    events: body.events,
  };
}

function startSession(baseUrl: string, options: RelaySessionOptions): Promise<DevSessionResult> {
  if (options.apiKey) {
    return createSession(baseUrl, { apiKey: options.apiKey, agentId: options.agentId });
  }
  if (!options.projectId) {
    throw new Error("createRelaySession needs `apiKey` (or `projectId` for a local dev gateway)");
  }
  return createDevSession(baseUrl, { projectId: options.projectId, agentId: options.agentId });
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
  const actionSpecs = new Map<string, ActionSpec>();
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
      const returned = await handler(params, { actionId, name });
      const result =
        returned && typeof returned === "object" && !Array.isArray(returned) ? returned : { ok: true };
      sendJson({
        type: "ACTION_APPLIED",
        action: name,
        action_id: actionId,
        result,
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

  /** App handlers must never break the session (connect, event stream): log and continue. */
  const safely = (handler: (event: RelayEventEnvelope) => void, event: RelayEventEnvelope) => {
    try {
      handler(event);
    } catch (err) {
      console.error(`relay: handler for ${event.type} threw`, err);
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
      for (const handler of handlers) safely(handler, event);
    }
    if (event.type === "ACTION_REQUESTED") {
      void handleActionRequested(event);
    }
    if (event.type === "APPROVAL_REQUESTED") {
      const approvalHandlers = typeHandlers.get("approval_requested");
      if (approvalHandlers) {
        for (const handler of approvalHandlers) safely(handler, event);
      }
    }
    if (event.type === "TRANSCRIPT_FINAL") {
      const transcriptHandlers = typeHandlers.get("transcript");
      if (transcriptHandlers) {
        for (const handler of transcriptHandlers) safely(handler, event);
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
        const created = await startSession(baseUrl, options);
        sessionId = created.sessionId;
        devToken = created.devToken;
        for (const event of created.events) emit(event);
      }
      const wsUrl = baseUrl.replace(/^http/, "ws");
      // Browsers cannot set WebSocket headers, so the token travels as a subprotocol — not in the URL.
      socket = new WebSocket(`${wsUrl}/ws/sessions/${sessionId}`, ["relay.v1", `relay.token.${devToken!}`]);
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
      advertiseActions(); // actions registered before connect()
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

  const advertiseActions = () => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const actions = [...actionSpecs].map(([name, spec]) => ({
      name,
      description: spec.description,
      parameters: spec.parameters ?? { type: "object", properties: {} },
    }));
    socket.send(JSON.stringify({ type: "APP_EVENT", name: CLIENT_CAPABILITIES_EVENT, payload: { actions } }));
  };

  const registerAction = (name: string, handler: ActionHandler, spec?: ActionSpec) => {
    actionHandlers.set(name, handler);
    if (spec) {
      actionSpecs.set(name, spec);
      advertiseActions();
    }
    return () => {
      if (actionHandlers.get(name) === handler) actionHandlers.delete(name);
      if (spec && actionSpecs.get(name) === spec) {
        actionSpecs.delete(name);
        advertiseActions();
      }
    };
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
