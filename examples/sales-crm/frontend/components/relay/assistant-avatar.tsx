"use client"

import * as React from "react"
import { PlayIcon } from "lucide-react"
import { mountAvatar, type AssistantState, type AvatarSession } from "@sumukhj1219-wkt-org/relay-web-sdk/avatar"

import { Button } from "@/components/ui/button"
import { useRelay } from "@/components/relay/relay-provider"
import { cn } from "@/lib/utils"

// Set NEXT_PUBLIC_RELAY_AVATAR=off to hide it.
const ENABLED = process.env.NEXT_PUBLIC_RELAY_AVATAR !== "off"

const LABELS: Record<AssistantState, string> = {
  idle: "",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking",
}

type Handler = Parameters<AvatarSession["on"]>[1]

/**
 * What the avatar listens to: the live session's events plus locally simulated ones (the Test button),
 * so the avatar can be tried without the gateway.
 */
function withSimulation(session: AvatarSession | null) {
  const local = new Map<string, Set<Handler>>()
  return {
    on(type: string, handler: Handler) {
      if (!local.has(type)) local.set(type, new Set())
      local.get(type)!.add(handler)
      const offLive = session?.on(type, handler)
      return () => {
        local.get(type)?.delete(handler)
        offLive?.()
      }
    },
    emit(type: string) {
      for (const handler of local.get(type) ?? []) handler({ type, payload: {} })
    },
  }
}

/** Video avatar: the talking loop plays while the assistant speaks (voice) or streams a reply (text); otherwise the idle loop. */
export function AssistantAvatar({ className }: { className?: string }) {
  const { getSession, connection } = useRelay()
  const ref = React.useRef<HTMLDivElement>(null)
  const [state, setState] = React.useState<AssistantState>("idle")
  const [testing, setTesting] = React.useState(false)
  const mounted = React.useRef<{
    session: object | null
    events: ReturnType<typeof withSimulation>
    destroy: () => void
  } | null>(null)
  const timers = React.useRef<ReturnType<typeof setTimeout>[]>([])

  // Re-checked on every connection change: a reconnect creates a new session, so remount on it.
  // Mounts without a session too, so the Test button works while the gateway is offline.
  React.useEffect(() => {
    const session = getSession()
    if (!ENABLED || !ref.current || (mounted.current && mounted.current.session === session)) return
    mounted.current?.destroy()
    const events = withSimulation(session)
    const avatar = mountAvatar(ref.current, events, {
      talking: "/avatar/talking.mp4",
      idle: "/avatar/idle.mp4", // a blink and glance, also used while listening and thinking
      poster: "/avatar/still.jpg",
      idleInterval: [6000, 14000], // mostly the still image; the idle clip once every 6–14 s
      label: "Relay assistant",
      onStateChange: setState,
    })
    mounted.current = { session, events, destroy: () => avatar.destroy() }
  }, [connection, getSession])

  const stopTest = React.useCallback(() => {
    for (const timer of timers.current) clearTimeout(timer)
    timers.current = []
  }, [])

  React.useEffect(
    () => () => {
      stopTest()
      mounted.current?.destroy()
      mounted.current = null
    },
    [stopTest],
  )

  /** Silent preview: thinking for a moment, the talking loop for a few seconds, then idle. */
  const runTest = () => {
    const events = mounted.current?.events
    if (!events || testing) return
    setTesting(true)
    const later = (ms: number, fn: () => void) => timers.current.push(setTimeout(fn, ms))
    events.emit("TURN_STARTED")
    later(1200, () => events.emit("SPEECH_STARTED"))
    later(6200, () => {
      events.emit("SPEECH_STOPPED")
      events.emit("TURN_COMPLETED")
    })
    later(6600, () => setTesting(false)) // after the speaking hold, so the button matches the avatar
  }

  if (!ENABLED) return null
  return (
    <div className={cn("flex flex-col items-center gap-1.5", className)}>
      <div
        ref={ref}
        className={cn(
          "size-36 overflow-hidden rounded-2xl bg-muted ring-offset-2 ring-offset-background transition-shadow",
          "data-[relay-avatar-state=speaking]:ring-2 data-[relay-avatar-state=speaking]:ring-primary",
          "data-[relay-avatar-state=listening]:ring-2 data-[relay-avatar-state=listening]:ring-emerald-500",
          "data-[relay-avatar-state=thinking]:ring-2 data-[relay-avatar-state=thinking]:ring-muted-foreground/40",
        )}
      />
      <div className="flex h-7 items-center gap-2">
        <span className="text-xs text-muted-foreground" aria-live="polite">
          {LABELS[state]}
        </span>
        {!testing && state === "idle" && (
          <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs" onClick={runTest}>
            <PlayIcon className="size-3" />
            Test avatar
          </Button>
        )}
      </div>
    </div>
  )
}
