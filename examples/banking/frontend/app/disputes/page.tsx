import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { bank } from "@/lib/bank"
import { longDate, rupees, statusLabel } from "@/lib/format"
import { DISPUTE_REASONS, type Dispute } from "@/lib/types"

export default async function DisputesPage() {
  const { disputes } = await bank<{ disputes: Dispute[] }>("/api/disputes")
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Disputes</h1>
        <p className="text-sm text-muted-foreground">Payments you&apos;ve asked us to look into. Raise a new one from the transaction.</p>
      </div>
      {disputes.length === 0 ? (
        <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          No disputes. Open a <Link href="/transactions" className="text-primary hover:underline">transaction</Link> to raise one.
        </p>
      ) : (
        <ul className="divide-y rounded-2xl border bg-card">
          {disputes.map((d) => (
            <li key={d.id}>
              <Link href={`/transactions/${d.transaction_id}`} className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-muted/50">
                <div className="flex flex-col">
                  <span className="font-medium">
                    {d.id} · {d.merchant} · {rupees(d.amount)}
                  </span>
                  <span className="text-muted-foreground">
                    {DISPUTE_REASONS[d.reason]} · update by {longDate(d.expected_by)}
                  </span>
                </div>
                <Badge variant="secondary">{statusLabel(d.status)}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
