"use client"

import { useRelay } from "@/components/relay/relay-provider"

/** Opens the assistant panel (it is docked on desktop; on phones it's a drawer). */
export function AssistantButton({ compact }: { compact?: boolean }) {
  const relay = useRelay()
  return (
    <button
      type="button"
      onClick={() => relay.setPanelOpen(!relay.panelOpen)}
      className="rounded-full border-2 border-[#e39b2d] bg-[#6e1423] px-3 py-1 text-[11px] font-bold text-white shadow hover:bg-[#8f1d30]"
      aria-pressed={relay.panelOpen}
      data-relay-ignore
    >
      {compact ? "Sahayak" : "🗣 Ask VNB Sahayak (voice / chat)"}
    </button>
  )
}
