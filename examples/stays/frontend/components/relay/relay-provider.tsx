"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import {
  createRelaySession,
  registerAutoNavigation,
  registerFormFill,
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
const AGENT_ID = process.env.NEXT_PUBLIC_AGENT_ID ?? "stays"
// Experience Center: every visitor has a private copy of the site (lib/session.ts).
export const SANDBOX = ["1", "true", "yes"].includes((process.env.NEXT_PUBLIC_RELAY_SANDBOX ?? "").toLowerCase())
const FORM_PREFIX = "[Form submitted]"
// Pages no on-screen link points to (the rest are found from the header and page links).
const EXTRA_PAGES = [
  { path: "/search", title: "All homes" },
  { path: "/trips?status=cancelled", title: "Cancelled trips" },
]

export type ChatMessage = { id: string; role: "user" | "assistant" | "system"; text: string }
export type FormStatus = { state: "saving" | "saved" | "failed"; error?: string }
export type PendingApproval = { approvalId: string; summary: string; toolName: string; arguments: Record<string, unknown> }
export type FormValues = Record<string, string | number | boolean | null>
type Session = ReturnType<typeof createRelaySession>
type ActionEntry = { name: string; handler: ActionHandler; spec: ActionSpec; off?: () => void }

type RelayContextValue = {
  connection: RelayConnectionState
  voice: VoiceConnectionState
  micMuted: boolean
  agentSpeaking: boolean
  busy: boolean
  messages: ChatMessage[]
  liveTranscript: string
  error: string | null
  approvals: PendingApproval[]
  approve: (approvalId: string) => void
  reject: (approvalId: string) => void
  panelOpen: boolean
  setPanelOpen: (open: boolean) => void
  sendText: (text: string) => void
  toggleVoice: () => Promise<void>
  toggleMute: () => void
  reconnect: () => void
  resetSandbox: () => Promise<void>
  // Results canvas (kept here, above the panel, so it outlives the panel).
  surfaces: UiSurface[]
  canvasHidden: boolean
  setCanvasHidden: (hidden: boolean) => void
  removeSurface: (index: number) => void
  clearSurfaces: () => void
  // Forms on the canvas: values (merged with chat fills), save state, recently filled fields.
  formValues: Record<string, FormValues>
  setFormValue: (formId: string, name: string, value: string | number | boolean | null) => void
  filledFields: Record<string, string[]>
  formStatus: Record<string, FormStatus>
  submitForm: (form: UiFormSurface, values: FormValues) => void
  registerAction: (name: string, handler: ActionHandler, spec: ActionSpec) => () => void
  publishScreenState: (key: string, value: unknown) => void
}

const RelayContext = React.createContext<RelayContextValue | null>(null)

export function useRelay(): RelayContextValue {
  const value = React.useContext(RelayContext)
  if (!value) throw new Error("useRelay must be used inside <RelayProvider>")
  return value
}

/** Expose a screen action to the assistant while this component is mounted. */
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

/** Tell the assistant what this screen shows (merged into shared state while mounted). */
export function useScreenState(key: string, value: unknown) {
  const { publishScreenState } = useRelay()
  const json = JSON.stringify(value)
  React.useEffect(() => {
    publishScreenState(key, JSON.parse(json))
    return () => publishScreenState(key, null)
  }, [publishScreenState, key, json])
}

const DESKTOP_QUERY = "(min-width: 1024px)"
const DESKTOP = typeof window === "undefined" ? ({ matches: false } as MediaQueryList) : window.matchMedia(DESKTOP_QUERY)
function subscribeDesktop(onChange: () => void) {
  DESKTOP.addEventListener?.("change", onChange)
  return () => DESKTOP.removeEventListener?.("change", onChange)
}

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
function displayUserText(text: string): { role: ChatMessage["role"]; text: string; outcome?: string } {
  if (text.startsWith(FORM_PREFIX)) {
    return { role: "user", text: `Submitted form: ${text.slice(FORM_PREFIX.length).split(":")[0].trim()}` }
  }
  const outcome = /^\[Action (approved|rejected|failed)\] ([\s\S]*?)(?:\. Result: [\s\S]*)?$/.exec(text)
  if (outcome) {
    const label = { approved: "Done", rejected: "Declined", failed: "Couldn't complete" }[outcome[1] as "approved"]
    return { role: "system", text: `${label}: ${outcome[2]}`, outcome: outcome[1] }
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
  const [canvasHidden, setCanvasHidden] = React.useState(false)
  const [formValues, setFormValues] = React.useState<Record<string, FormValues>>({})
  const [filledFields, setFilledFields] = React.useState<Record<string, string[]>>({})
  const [error, setError] = React.useState<string | null>(null)
  // Docked open on desktop; on phones the panel is a drawer the guest opens from the header.
  const isDesktop = React.useSyncExternalStore(subscribeDesktop, () => DESKTOP.matches, () => false)
  const [panelChoice, setPanelOpen] = React.useState<boolean | null>(null)
  const panelOpen = panelChoice ?? isDesktop
  const [formStatus, setFormStatus] = React.useState<Record<string, FormStatus>>({})
  const [approvals, setApprovals] = React.useState<PendingApproval[]>([])
  const [generation, setGeneration] = React.useState(0)
  const [serverSession, setServerSession] = React.useState<{ generation: number; sessionId: string; token: string } | null>(null)
  const router = useRouter()
  const pathname = usePathname()
  const sessionRef = React.useRef<Session | null>(null)
  const actionsRef = React.useRef(new Map<string, ActionEntry>())
  const screenStateRef = React.useRef<Record<string, unknown>>({})
  const voiceRef = React.useRef<VoiceConnectionState>("disconnected")
  const surfacesRef = React.useRef<UiSurface[]>([])

  React.useEffect(() => {
    surfacesRef.current = surfaces
  }, [surfaces])

  // 1) The site's server starts the session for the signed-in guest (or the visitor's sandbox).
  React.useEffect(() => {
    let cancelled = false
    fetch("/api/assistant/session", { method: "POST" })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(body.error ?? `status ${res.status}`)
        if (!cancelled) setServerSession({ generation, sessionId: body.sessionId, token: body.token })
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(`Couldn't start the assistant (${e instanceof Error ? e.message : String(e)}).`)
      })
    return () => {
      cancelled = true
    }
  }, [generation])

  // 2) Connect to it, with every handler registered first.
  React.useEffect(() => {
    if (serverSession?.generation !== generation) return
    const session = createRelaySession({
      gatewayUrl: GATEWAY_URL,
      sessionId: serverSession.sessionId,
      devToken: serverSession.token,
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
    for (const entry of actions.values()) entry.off = session.registerAction(entry.name, entry.handler, entry.spec)
    const offSurfaces = registerPlaygroundSurfaces(session, (params) => {
      setSurfaces((current) => applyPresentUi(current, params))
      setCanvasHidden(false) // new results show the canvas again
    })
    const offFill = registerFormFill(session, ({ formId, values }) => {
      if (!surfacesRef.current.some((s) => s.kind === "form" && s.id === formId)) throw new Error("form is not open")
      setFormValues((all) => ({ ...all, [formId]: { ...all[formId], ...(values as FormValues) } }))
      setCanvasHidden(false)
      setFilledFields((all) => ({ ...all, [formId]: Object.keys(values) }))
      setTimeout(() => setFilledFields((all) => ({ ...all, [formId]: [] })), 1600)
    })
    const offNavigation = registerAutoNavigation(session, { navigate: (path) => router.push(path), pages: EXTRA_PAGES })
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
      const { outcome, ...line } = displayUserText(text)
      setMessages((prev) => [...prev, { id: String(e.metadata.event_id ?? crypto.randomUUID()), ...line }])
      if (outcome === "approved") router.refresh() // the approved change ran: re-read trips, calendars, wishlists
    })
    session.on("RESPONSE_STARTED", () => {
      assistant = { id: crypto.randomUUID(), text: "" }
    })
    session.on("RESPONSE_DELTA", (e: RelayEventEnvelope) => {
      if (!assistant) return
      assistant.text += String(e.payload.text ?? "")
      if (voiceRef.current !== "connected") upsert(assistant.id, assistant.text)
    })
    const heard = (e: RelayEventEnvelope) => {
      const text = String(e.payload.heard_text ?? "")
      if (assistant && text) upsert(assistant.id, text)
    }
    session.on("SPEECH_PROGRESS", heard)
    session.on("RESPONSE_INTERRUPTED", heard)
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
    const settle = (e: RelayEventEnvelope) => setApprovals((prev) => prev.filter((a) => a.approvalId !== e.payload.approval_id))
    session.on("APPROVAL_GRANTED", settle)
    session.on("APPROVAL_REJECTED", settle)
    session.on("COMMIT_VERIFIED", (e: RelayEventEnvelope) => {
      const formId = String(e.payload.form_id ?? "")
      if (formId) setFormStatus((prev) => ({ ...prev, [formId]: { state: "saved" } }))
      router.refresh()
    })
    session.on("ERROR", (e: RelayEventEnvelope) => {
      if (e.payload.message !== "commit_failed") return
      const formId = String(e.payload.form_id ?? "")
      if (formId) setFormStatus((prev) => ({ ...prev, [formId]: { state: "failed", error: String(e.payload.error ?? "") } }))
    })
    session.on("SESSION_ERROR", (e: RelayEventEnvelope) => {
      setBusy(false)
      setError(String(e.payload.message ?? "Something went wrong"))
    })

    session
      .connect()
      .then(() => {
        if (Object.keys(screenStateRef.current).length) session.sendState(screenStateRef.current)
      })
      .catch((e: unknown) => {
        setError(`Couldn't connect to the assistant (${e instanceof Error ? e.message : String(e)}).`)
      })

    return () => {
      offSurfaces()
      offFill()
      offNavigation()
      offPageForms()
      for (const entry of actions.values()) entry.off = undefined
      session.disconnect()
      if (sessionRef.current === session) sessionRef.current = null
    }
  }, [generation, router, serverSession])

  const registerAction = React.useCallback((name: string, handler: ActionHandler, spec: ActionSpec) => {
    const entry: ActionEntry = { name, handler, spec }
    actionsRef.current.get(name)?.off?.()
    actionsRef.current.set(name, entry)
    if (sessionRef.current) entry.off = sessionRef.current.registerAction(name, handler, spec)
    return () => {
      if (actionsRef.current.get(name) === entry) actionsRef.current.delete(name)
      entry.off?.()
    }
  }, [])

  const publishScreenState = React.useCallback((key: string, value: unknown) => {
    const next = { ...screenStateRef.current }
    if (value === null) delete next[key]
    else next[key] = value
    screenStateRef.current = next
    const session = sessionRef.current
    if (session?.connectionState === "ready") {
      try {
        session.sendState(next)
      } catch {
        /* reconnecting; sent again after connect */
      }
    }
  }, [])

  // Where the guest is, on every route change.
  React.useEffect(() => {
    publishScreenState("page", { path: pathname })
  }, [pathname, publishScreenState])

  const reconnect = () => {
    setError(null)
    setMessages([])
    setSurfaces([])
    setApprovals([])
    setBusy(false)
    setGeneration((g) => g + 1)
  }

  const value: RelayContextValue = {
    connection,
    voice,
    micMuted,
    agentSpeaking,
    busy,
    messages,
    liveTranscript,
    error,
    approvals,
    approve: (approvalId) => sessionRef.current?.grantApproval(approvalId),
    reject: (approvalId) => sessionRef.current?.rejectApproval(approvalId),
    panelOpen,
    setPanelOpen,
    sendText: (text) => {
      const trimmed = text.trim()
      if (!trimmed || !sessionRef.current) return
      setError(null)
      try {
        sessionRef.current.sendText(trimmed)
      } catch {
        setError("Not connected to the assistant.")
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
    reconnect,
    resetSandbox: async () => {
      await fetch("/api/sandbox/reset", { method: "POST" }).catch(() => undefined)
      setFormStatus({})
      setFormValues({})
      reconnect()
      router.refresh()
    },
    surfaces,
    canvasHidden,
    setCanvasHidden,
    removeSurface: (index) => setSurfaces((current) => current.filter((_, i) => i !== index)),
    clearSurfaces: () => setSurfaces([]),
    formValues,
    setFormValue: (formId, name, v) => setFormValues((all) => ({ ...all, [formId]: { ...all[formId], [name]: v } })),
    filledFields,
    formStatus,
    submitForm: (form, values) => {
      if (!sessionRef.current) return
      if (form.submitTool) setFormStatus((prev) => ({ ...prev, [form.id]: { state: "saving" } }))
      sendFormValues(sessionRef.current, form, values)
    },
    registerAction,
    publishScreenState,
  }

  return <RelayContext.Provider value={value}>{children}</RelayContext.Provider>
}
