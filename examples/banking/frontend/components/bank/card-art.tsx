import type { Card } from "@/lib/types"
import { cn } from "@/lib/utils"

/** The card face: navy for credit, teal for debit; dimmed when not usable. */
export function CardArt({ card, className }: { card: Pick<Card, "kind" | "name" | "network" | "last4" | "expires" | "status">; className?: string }) {
  const usable = card.status === "active"
  return (
    <div
      className={cn(
        "relative flex aspect-[1.586] w-full max-w-sm flex-col justify-between overflow-hidden rounded-2xl p-5 text-white shadow-md",
        card.kind === "credit" ? "bg-gradient-to-br from-[oklch(0.3_0.1_265)] to-[oklch(0.45_0.14_280)]" : "bg-gradient-to-br from-[oklch(0.4_0.08_200)] to-[oklch(0.55_0.1_175)]",
        !usable && "opacity-60 grayscale",
        className,
      )}
    >
      <div className="flex items-start justify-between">
        <span className="text-sm font-medium">{card.name}</span>
        <span className="text-xs font-semibold tracking-wider uppercase">{card.kind}</span>
      </div>
      <div className="h-7 w-10 rounded-md bg-gradient-to-br from-amber-200 to-amber-400 opacity-90" aria-hidden />
      <div className="flex items-end justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-lg tracking-widest">•••• {card.last4}</span>
          <span className="text-xs opacity-80">Valid thru {card.expires}</span>
        </div>
        <span className="text-lg font-bold italic">{card.network}</span>
      </div>
      {!usable && (
        <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/60 px-3 py-1 text-xs font-semibold uppercase">
          {card.status.replace(/_/g, " ")}
        </span>
      )}
    </div>
  )
}
