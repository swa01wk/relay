"use client"

import { useEffect, useState } from "react"

/**
 * The hero's live-looking trace: what a user says and the Relay Protocol events that follow.
 * Event names are the real RP catalog (packages/protocol); payloads are trimmed for display.
 */
type Line = { type: string; detail: string; tone: "user" | "tool" | "ui" | "approval" | "speech" | "done" }
type Script = { said: string; lines: Line[] }

const scripts: Script[] = [
  {
    said: "Show me deals closing this month as a chart",
    lines: [
      { type: "TRANSCRIPT_FINAL", detail: '"Show me deals closing this month…"', tone: "user" },
      { type: "TOOL_CALL_STARTED", detail: "list_deals { close: this_month }", tone: "tool" },
      { type: "TOOL_CALL_COMPLETED", detail: "14 deals", tone: "tool" },
      { type: "ACTION_REQUESTED", detail: "navigate → /dashboard", tone: "ui" },
      { type: "ACTION_APPLIED", detail: "route changed", tone: "ui" },
      { type: "ACTION_REQUESTED", detail: "PRESENT_UI · chart · deals by stage", tone: "ui" },
      { type: "SPEECH_STARTED", detail: '"Fourteen deals close this month…"', tone: "speech" },
      { type: "TURN_COMPLETED", detail: "chart on screen, answer spoken", tone: "done" },
    ],
  },
  {
    said: "Move Northwind to Closed Won",
    lines: [
      { type: "TRANSCRIPT_FINAL", detail: '"Move Northwind to Closed Won"', tone: "user" },
      { type: "TOOL_CALL_STARTED", detail: "search_accounts { query: Northwind }", tone: "tool" },
      { type: "TOOL_CALL_COMPLETED", detail: "ACC-001 · DEAL-2041", tone: "tool" },
      { type: "APPROVAL_REQUESTED", detail: "update_deal · stage → Closed Won", tone: "approval" },
      { type: "APPROVAL_GRANTED", detail: "approved in the assistant panel", tone: "approval" },
      { type: "COMMIT_VERIFIED", detail: "DEAL-2041 saved", tone: "done" },
      { type: "SPEECH_STARTED", detail: '"Done — Northwind is Closed Won."', tone: "speech" },
    ],
  },
  {
    said: "Actually, make that next quarter—",
    lines: [
      { type: "INTERRUPTION_DETECTED", detail: "user spoke over the reply", tone: "user" },
      { type: "RESPONSE_INTERRUPTED", detail: 'heard: "Here are the deals for—"', tone: "speech" },
      { type: "HEARD_TEXT_COMMITTED", detail: "context keeps only what was heard", tone: "speech" },
      { type: "TOOL_CALL_STARTED", detail: "list_deals { close: next_quarter }", tone: "tool" },
      { type: "STATE_DELTA", detail: "filters.close = next_quarter · v12", tone: "ui" },
      { type: "TURN_COMPLETED", detail: "barge-in handled", tone: "done" },
    ],
  },
]

const toneClass: Record<Line["tone"], string> = {
  user: "text-fg",
  tool: "text-violet",
  ui: "text-accent",
  approval: "text-warn",
  speech: "text-rose",
  done: "text-muted",
}

export function EventStream() {
  const [scriptIndex, setScriptIndex] = useState(0)
  const [shown, setShown] = useState(0)
  const script = scripts[scriptIndex]

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const done = shown >= script.lines.length
    const timer = setTimeout(
      () => {
        if (reduced) setShown(script.lines.length) // no animation: the whole first trace, once
        else if (done) {
          setShown(0)
          setScriptIndex((i) => (i + 1) % scripts.length)
        } else setShown((n) => n + 1)
      },
      reduced ? 0 : done ? 2600 : shown === 0 ? 900 : 520,
    )
    return () => clearTimeout(timer)
  }, [shown, script.lines.length])

  return (
    <div className="overflow-hidden rounded-xl border border-line-strong bg-sunken shadow-2xl shadow-black/30">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="ml-2 font-mono text-xs text-faint">ws /sessions/…/events</span>
        <span className="ml-auto flex items-center gap-1.5 font-mono text-xs text-accent">
          <span className="size-1.5 rounded-full bg-accent" /> live
        </span>
      </div>
      <div className="border-b border-line px-4 py-3">
        <p className="font-mono text-[11px] uppercase tracking-wider text-faint">user said</p>
        <p className="mt-1 text-sm text-fg">
          {script.said}
          <span className="caret ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-accent" />
        </p>
      </div>
      <ol className="h-[17.5rem] space-y-1.5 px-4 py-3 font-mono text-[12px] leading-5" aria-live="off">
        {script.lines.slice(0, shown).map((line, i) => (
          <li key={`${scriptIndex}-${i}`} className="event-in flex min-w-0 gap-3">
            <span className="w-5 shrink-0 text-right text-faint">{i}</span>
            <span className={`shrink-0 ${toneClass[line.tone]}`}>{line.type}</span>
            <span className="truncate text-faint">{line.detail}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
