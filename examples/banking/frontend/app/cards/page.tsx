import Link from "next/link"

import { CardArt } from "@/components/bank/card-art"
import { bank } from "@/lib/bank"
import { rupees, shortDate } from "@/lib/format"
import type { Card } from "@/lib/types"

export default async function CardsPage() {
  const { cards } = await bank<{ cards: Card[] }>("/api/cards")
  const live = cards.filter((c) => c.status !== "blocked")
  const blocked = cards.filter((c) => c.status === "blocked")
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Cards</h1>
        <p className="text-sm text-muted-foreground">Lock a card, change where it works and its limits, or pay your credit card.</p>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        {live.map((c) => (
          <Link key={c.id} href={`/cards/${c.id}`} className="flex flex-col gap-4 rounded-2xl border bg-card p-5 hover:border-primary" data-testid={`card-${c.id}`}>
            <CardArt card={c} />
            <div className="flex flex-col gap-1 text-sm">
              {c.kind === "credit" ? (
                <>
                  <span>
                    Outstanding <span className="font-medium tabular-nums">{rupees(c.outstanding ?? 0)}</span> of {rupees(c.credit_limit ?? 0)}
                  </span>
                  {c.statement && (
                    <span className="text-muted-foreground">
                      {c.statement.total_due_now > 0 ? `${rupees(c.statement.total_due_now)} due ${shortDate(c.statement.due_date)}` : "Statement paid"} ·{" "}
                      {(c.reward_points ?? 0).toLocaleString("en-IN")} points
                    </span>
                  )}
                </>
              ) : (
                <span className="text-muted-foreground">Linked to {c.account_label}</span>
              )}
              {c.status === "on_the_way" && c.arrives_on && <span className="text-amber-700">On the way — arrives by {shortDate(c.arrives_on)}</span>}
            </div>
          </Link>
        ))}
      </div>
      {blocked.length > 0 && (
        <p className="text-sm text-muted-foreground">
          Blocked:{" "}
          {blocked.map((c, i) => (
            <span key={c.id}>
              {i > 0 && ", "}
              <Link href={`/cards/${c.id}`} className="hover:underline">
                {c.name} ••{c.last4}
              </Link>
            </span>
          ))}
        </p>
      )}
    </div>
  )
}
