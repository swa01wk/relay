"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  createRelaySession,
  registerAutoNavigation,
  registerPageForms,
  registerPlaygroundSurfaces,
  submitForm as sendFormValues,
  type ActionHandler,
  type ActionSpec,
  type PresentUiParams,
  type RelayConnectionState,
  type RelayEventEnvelope,
  type UiFormSurface,
  type UiSurface,
  type VoiceConnectionState,
} from "@sumukhj1219-wkt-org/relay-web-sdk"

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080"
const PROJECT_ID = process.env.NEXT_PUBLIC_PROJECT_ID ?? "proj-sales-crm"
// Publishable project key (`relay keys create --kind publishable`). Without it the app uses a
// local dev gateway (RELAY_DEV_SESSIONS=1), where the project id is enough.
const API_KEY = process.env.NEXT_PUBLIC_RELAY_API_KEY
const AGENT_ID = process.env.NEXT_PUBLIC_AGENT_ID ?? "sales-crm"
const FORM_PREFIX = "[Form submitted]"

export type ChatMessage = { id: string; role: "user" | "assistant" | "system"; text: string }
export type FormStatus = { state: "saving" | "saved" | "failed"; error?: string }
export type PendingApproval = { approvalId: string; summary: string; toolName: string; arguments: Record<string, unknown> }
export type FormValues = Record<string, string | number | boolean | null>
type Session = ReturnType<typeof createRelaySession>
type ActionEntry = { name: string; handler: ActionHandler; spec: ActionSpec; off?: () => void }

type RelayContextValue = {
  /** The live session (null between reconnects), for SDK helpers such as the avatar. Re-read when `connection` changes. */
  getSession: () => Session | null
  connection: RelayConnectionState
  voice: VoiceConnectionState
  micMuted: boolean
  agentSpeaking: boolean
  busy: boolean
  messages: ChatMessage[]
  liveTranscript: string
  surfaces: UiSurface[]
  error: string | null
  /** Save state of tool-bound forms, by form id. */
  formStatus: Record<string, FormStatus>
  /** Changes the assistant proposed that wait for the user's decision. */
  approvals: PendingApproval[]
  approve: (approvalId: string) => void
  reject: (approvalId: string) => void
  panelOpen: boolean
  setPanelOpen: (open: boolean) => void
  sendText: (text: string) => void
  toggleVoice: () => Promise<void>
  toggleMute: () => void
  submitForm: (form: UiFormSurface, values: FormValues) => void
  clearSurfaces: () => void
  reconnect: () => void
  /** Register an app action the agent may call (prefer `useRelayAction`). Returns unregister. */
  registerAction: (name: string, handler: ActionHandler, spec: ActionSpec) => () => void
  /** Tell the agent what is on screen (merged into shared state; sent when connected). */
  publishScreenState: (key: string, value: unknown) => void
}

const RelayContext = React.createContext<RelayContextValue | null>(null)

export function useRelay(): RelayContextValue {
  const value = React.useContext(RelayContext)
  if (!value) throw new Error("useRelay must be used inside <RelayProvider>")
  return value
}

/** Expose a screen action to the agent while this component is mounted. */
export function useRelayAction(name: string, handler: ActionHandler, spec: ActionSpec) {
  const { registerAction } = useRelay()
  const handlerRef = React.useRef(handler)
  React.useEffect(() => {
    handlerRef.current = handler
  })
  const specKey = JSON.stringify(spec)
  React.useEffect(
    () => registerAction(name, (params, ctx) => handlerRef.current(params, ctx), JSON.parse(specKey)),
    [registerAction, name, specKey],
  )
}

/** Replace the canvas, or append (a surface with the same id updates in place). */
function applyPresentUi(current: UiSurface[], params: PresentUiParams): UiSurface[] {
  if (params.replace) return params.surfaces
  const next = [...current]
  for (const surface of params.surfaces) {
    const index = surface.id ? next.findIndex((s) => s.id === surface.id) : -1
    if (index >= 0) next[index] = surface
    else next.push(surface)
  }
  return next
}

/** Runtime-generated user turns (form submissions, approval outcomes) shown as short notes. */
function displayUserText(text: string): { role: ChatMessage["role"]; text: string } {
  if (text.startsWith(FORM_PREFIX)) {
    return { role: "user", text: `Submitted form: ${text.slice(FORM_PREFIX.length).split(":")[0].trim()}` }
  }
  const outcome = /^\[Action (approved|rejected|failed)\] ([\s\S]*?)(?:\. Result: [\s\S]*)?$/.exec(text)
  if (outcome) {
    const label = { approved: "Saved", rejected: "Declined", failed: "Couldn't save" }[outcome[1] as "approved"]
    return { role: "system", text: `${label}: ${outcome[2]}` }
  }
  return { role: "user", text }
}

export function RelayProvider({ children }: { children: React.ReactNode }) {
  const [connection, setConnection] = React.useState<RelayConnectionState>("disconnected")
  const [voice, setVoice] = React.useState<VoiceConnectionState>("disconnected")
  const [micMuted, setMicMuted] = React.useState(false)
  const [agentSpeaking, setAgentSpeaking] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const [liveTranscript, setLiveTranscript] = React.useState("")
  const [surfaces, setSurfaces] = React.useState<UiSurface[]>([])
  const [error, setError] = React.useState<string | null>(null)
  const [panelOpen, setPanelOpen] = React.useState(true)
  const [formStatus, setFormStatus] = React.useState<Record<string, FormStatus>>({})
  const [approvals, setApprovals] = React.useState<PendingApproval[]>([])
  const router = useRouter()
  const [generation, setGeneration] = React.useState(0)
  const sessionRef = React.useRef<Session | null>(null)
  // Actions survive reconnects and may be registered before the session exists.
  const actionsRef = React.useRef(new Map<string, ActionEntry>())
  const screenStateRef = React.useRef<Record<string, unknown>>({})
  const voiceRef = React.useRef<VoiceConnectionState>("disconnected")

  React.useEffect(() => {
    const session = createRelaySession({
      gatewayUrl: GATEWAY_URL,
      ...(API_KEY ? { apiKey: API_KEY } : { projectId: PROJECT_ID }),
      agentId: AGENT_ID,
      transport: "small-webrtc",
    })
    sessionRef.current = session
    let assistant: { id: string; text: string } | null = null

    const upsert = (id: string, text: string) =>
      setMessages((prev) =>
        prev.some((m) => m.id === id)
          ? prev.map((m) => (m.id === id ? { ...m, text } : m))
          : [...prev, { id, role: "assistant", text }],
      )

    const actions = actionsRef.current
    for (const entry of actions.values()) {
      entry.off = session.registerAction(entry.name, entry.handler, entry.spec)
    }
    // Handlers first, then connect, so no early event is missed.
    const offSurfaces = registerPlaygroundSurfaces(session, (params) => {
      setSurfaces((current) => applyPresentUi(current, params))
    })
    // "Go to the dashboard": every page the sidebar links to, opened with the Next.js router.
    const offNavigation = registerAutoNavigation(session, { navigate: (path) => router.push(path) })
    // "Fill this form": the app's own forms on screen (canvas forms and the chat input are marked data-relay-ignore).
    const offPageForms = registerPageForms(session)
    session.onConnectionState(setConnection)
    session.onVoiceState((state) => {
      voiceRef.current = state
      setVoice(state)
    })
    session.on("TURN_STARTED", () => setBusy(true))
    session.on("TURN_COMPLETED", () => setBusy(false))
    session.on("TRANSCRIPT_DELTA", (e: RelayEventEnvelope) => setLiveTranscript(String(e.payload.text ?? "")))
    session.on("TRANSCRIPT_FINAL", (e: RelayEventEnvelope) => {
      setLiveTranscript("")
      const text = String(e.payload.text ?? "")
      if (!text) return
      const id = String(e.metadata.event_id ?? crypto.randomUUID())
      setMessages((prev) => [...prev, { id, ...displayUserText(text) }])
    })
    session.on("RESPONSE_STARTED", () => {
      assistant = { id: crypto.randomUUID(), text: "" }
    })
    session.on("RESPONSE_DELTA", (e: RelayEventEnvelope) => {
      if (!assistant) return
      assistant.text += String(e.payload.text ?? "")
      // With voice on, show what was actually heard (SPEECH_PROGRESS) instead of the raw stream.
      if (voiceRef.current !== "connected") upsert(assistant.id, assistant.text)
    })
    session.on("SPEECH_PROGRESS", (e: RelayEventEnvelope) => {
      const heard = String(e.payload.heard_text ?? "")
      if (assistant && heard) upsert(assistant.id, heard)
    })
    session.on("RESPONSE_INTERRUPTED", (e: RelayEventEnvelope) => {
      const heard = String(e.payload.heard_text ?? "")
      if (assistant && heard) upsert(assistant.id, heard)
    })
    session.on("RESPONSE_COMPLETED", (e: RelayEventEnvelope) => {
      if (assistant) upsert(assistant.id, String(e.payload.text ?? "") || assistant.text)
      assistant = null
    })
    session.on("agent_activity", (e: RelayEventEnvelope) => setAgentSpeaking(Boolean(e.payload.speaking)))
    session.on("APPROVAL_REQUESTED", (e: RelayEventEnvelope) => {
      const p = e.payload
      setPanelOpen(true) // approvals are answered in the assistant panel
      setApprovals((prev) => [
        ...prev.filter((a) => a.approvalId !== p.approval_id),
        {
          approvalId: String(p.approval_id),
          summary: String(p.summary ?? p.tool_name ?? "Proposed change"),
          toolName: String(p.tool_name ?? ""),
          arguments: (p.arguments ?? {}) as Record<string, unknown>,
        },
      ])
    })
    const settle = (e: RelayEventEnvelope) =>
      setApprovals((prev) => prev.filter((a) => a.approvalId !== e.payload.approval_id))
    session.on("APPROVAL_GRANTED", settle)
    session.on("APPROVAL_REJECTED", settle)
    session.on("COMMIT_VERIFIED", (e: RelayEventEnvelope) => {
      const formId = String(e.payload.form_id ?? "")
      if (formId) setFormStatus((prev) => ({ ...prev, [formId]: { state: "saved" } }))
      router.refresh() // re-fetch dashboard data (server component)
    })
    session.on("ERROR", (e: RelayEventEnvelope) => {
      if (e.payload.message !== "commit_failed") return
      const formId = String(e.payload.form_id ?? "")
      if (formId) {
        setFormStatus((prev) => ({ ...prev, [formId]: { state: "failed", error: String(e.payload.error ?? "") } }))
      }
    })
    session.on("SESSION_ERROR", (e: RelayEventEnvelope) => {
      setBusy(false)
      setError(String(e.payload.message ?? "Something went wrong"))
    })

    session
      .connect()
      .then(() => {
        // Screen state can only be sent once the WebSocket is open.
        if (Object.keys(screenStateRef.current).length) session.sendState(screenStateRef.current)
      })
      .catch((e: unknown) => {
        const reason = e instanceof Error ? e.message : String(e)
        setError(`Couldn't connect to the Relay gateway at ${GATEWAY_URL} (${reason}).`)
      })

    return () => {
      offSurfaces()
      offNavigation()
      offPageForms()
      for (const entry of actions.values()) entry.off = undefined
      session.disconnect()
      if (sessionRef.current === session) sessionRef.current = null
    }
  }, [generation, router])

  const registerAction = React.useCallback(
    (name: string, handler: ActionHandler, spec: ActionSpec) => {
      const entry: ActionEntry = { name, handler, spec }
      actionsRef.current.get(name)?.off?.()
      actionsRef.current.set(name, entry)
      if (sessionRef.current) entry.off = sessionRef.current.registerAction(name, handler, spec)
      return () => {
        if (actionsRef.current.get(name) === entry) actionsRef.current.delete(name)
        entry.off?.()
      }
    },
    [],
  )

  const publishScreenState = React.useCallback((key: string, value: unknown) => {
    screenStateRef.current = { ...screenStateRef.current, [key]: value }
    const session = sessionRef.current
    if (session?.connectionState === "ready") {
      try {
        session.sendState(screenStateRef.current)
      } catch {
        /* reconnecting; sent again on SESSION_READY */
      }
    }
  }, [])

  const getSession = React.useCallback(() => sessionRef.current, [])
  const value: RelayContextValue = {
    getSession,
    connection,
    voice,
    micMuted,
    agentSpeaking,
    busy,
    messages,
    liveTranscript,
    surfaces,
    error,
    panelOpen,
    setPanelOpen,
    sendText: (text) => {
      const trimmed = text.trim()
      if (!trimmed || !sessionRef.current) return
      setError(null)
      try {
        sessionRef.current.sendText(trimmed)
      } catch {
        setError("Not connected to Relay.")
      }
    },
    toggleVoice: async () => {
      const session = sessionRef.current
      if (!session) return
      setError(null)
      try {
        if (voice === "connected" || voice === "connecting") {
          await session.disconnectVoice()
          setMicMuted(false)
        } else {
          await session.connectVoice()
        }
      } catch {
        setError("Couldn't start voice. Check microphone permission.")
      }
    },
    toggleMute: () => {
      const next = !micMuted
      setMicMuted(next)
      sessionRef.current?.setMicMuted(next)
    },
    submitForm: (form, values) => {
      if (!sessionRef.current) return
      if (form.submitTool) setFormStatus((prev) => ({ ...prev, [form.id]: { state: "saving" } }))
      sendFormValues(sessionRef.current, form, values)
    },
    formStatus,
    approvals,
    approve: (approvalId) => sessionRef.current?.grantApproval(approvalId),
    reject: (approvalId) => sessionRef.current?.rejectApproval(approvalId),
    clearSurfaces: () => setSurfaces([]),
    registerAction,
    publishScreenState,
    reconnect: () => {
      setError(null)
      setMessages([])
      setSurfaces([])
      setBusy(false)
      setGeneration((g) => g + 1)
    },
  }

  return <RelayContext.Provider value={value}>{children}</RelayContext.Provider>
}
