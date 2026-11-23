"use client"

import { RotateCcwIcon, SparklesIcon } from "lucide-react"

import { SANDBOX, useRelay } from "@/components/relay/relay-provider"
import { Button } from "@/components/ui/button"

export function AssistantToggle() {
  const { panelOpen, setPanelOpen, approvals, busy } = useRelay()
  return (
    <Button
      variant={panelOpen ? "secondary" : "default"}
      size="sm"
      onClick={() => setPanelOpen(!panelOpen)}
      aria-pressed={panelOpen}
      className="relative"
    >
      <SparklesIcon className={busy ? "animate-pulse" : undefined} />
      <span className="hidden sm:inline">Assistant</span>
      {approvals.length > 0 && (
        <span className="absolute -top-1 -right-1 grid size-4 place-items-center rounded-full bg-amber-500 text-[10px] font-semibold text-white">
          {approvals.length}
        </span>
      )}
    </Button>
  )
}

export function ResetDemoButton() {
  const { resetSandbox } = useRelay()
  if (!SANDBOX) return null
  return (
    <Button
      variant="ghost"
      size="sm"
      title="Your payments, payees, cards and deposits are private to you. Reset puts the demo bank back."
      onClick={() => void resetSandbox()}
    >
      <RotateCcwIcon />
      <span className="hidden md:inline">Reset demo</span>
    </Button>
  )
}
