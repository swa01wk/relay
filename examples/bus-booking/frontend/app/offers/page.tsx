import { BadgePercentIcon } from "lucide-react"

import { ScreenState } from "@/components/bus/screen-state"
import { bus } from "@/lib/bus"
import type { Offer } from "@/lib/types"

export default async function OffersPage() {
  const { offers } = await bus<{ offers: Offer[] }>("/api/offers")
  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="offers" value={{ codes: offers.map((o) => o.code) }} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Offers</h1>
        <p className="text-sm text-muted-foreground">Enter a code on the passenger details page, or ask the assistant which one saves the most.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {offers.map((o) => (
          <div key={o.code} className="flex gap-4 rounded-2xl border border-dashed border-primary/40 bg-card p-5">
            <BadgePercentIcon className="size-6 shrink-0 text-primary" />
            <div>
              <p className="font-mono font-semibold tracking-wide text-primary">{o.code}</p>
              <p className="font-medium">{o.title}</p>
              <p className="text-sm text-muted-foreground">{o.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
