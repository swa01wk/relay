import Link from "next/link"
import { notFound } from "next/navigation"
import { TriangleAlertIcon } from "lucide-react"

import { DisputeForm } from "@/components/bank/dispute-form"
import { ScreenState } from "@/components/bank/screen-state"
import { CategoryIcon } from "@/components/bank/txn-table"
import { Badge } from "@/components/ui/badge"
import { bank, BankError } from "@/lib/bank"
import { dateTime, longDate, rupees, signed, statusLabel } from "@/lib/format"
import { CHANNELS, DISPUTE_REASONS, type TxnDetail } from "@/lib/types"
import { cn } from "@/lib/utils"

type Props = { params: Promise<{ id: string }> }

export default async function TransactionPage({ params }: Props) {
  const { id } = await params
  let t: TxnDetail
  try {
    t = (await bank<{ transaction: TxnDetail }>(`/api/transactions/${id}`)).transaction
  } catch (e) {
    if (e instanceof BankError && e.status === 404) notFound()
    throw e
  }
  const rows: [string, string][] = [
    ["Date", dateTime(t.posted_at)],
    ["Account", t.account],
    ["Category", t.category_label],
    ["Paid by", CHANNELS[t.channel] ?? t.channel],
    ["Reference", t.reference],
  ]
  if (t.payee) rows.push(["Payee", t.payee.label])
  if (t.note) rows.push(["Note", t.note])
  if (t.balance_after !== undefined) rows.push(["Balance after", rupees(t.balance_after)])

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <ScreenState name="transaction" value={{ id: t.id, can_dispute: t.can_dispute, duplicate: Boolean(t.possible_duplicate_of) }} />
      <Link href="/transactions" className="text-sm text-primary hover:underline">
        ← Transactions
      </Link>
      <section className="flex items-center gap-4">
        <CategoryIcon category={t.category} className="size-12" />
        <div className="flex-1">
          <h1 className="text-xl font-semibold">{t.description}</h1>
          <p className="text-sm text-muted-foreground">{t.merchant ?? t.category_label}</p>
        </div>
        <span className={cn("text-2xl font-semibold tabular-nums", t.direction === "credit" && "text-emerald-700")}>{signed(t.amount, t.direction)}</span>
      </section>
      {t.possible_duplicate_of && (
        <p className="flex items-center gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
          <TriangleAlertIcon className="size-4 shrink-0" /> Another charge of {rupees(t.amount)} at {t.merchant} on the same day:{" "}
          {t.possible_duplicate_of.map((d) => (
            <Link key={d} href={`/transactions/${d}`} className="underline">
              view it
            </Link>
          ))}
        </p>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 rounded-2xl border bg-card p-5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="text-right font-medium break-all">{v}</dd>
          </div>
        ))}
      </dl>
      {t.dispute ? (
        <section className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-sm">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Dispute {t.dispute.id}</h2>
            <Badge variant="secondary">{statusLabel(t.dispute.status)}</Badge>
          </div>
          <p>{DISPUTE_REASONS[t.dispute.reason]}</p>
          {t.dispute.details && <p className="text-muted-foreground">“{t.dispute.details}”</p>}
          {t.dispute.provisional_credit > 0 && <p className="text-emerald-700">{rupees(t.dispute.provisional_credit)} credited back provisionally.</p>}
          <p className="text-muted-foreground">We&apos;ll update you by {longDate(t.dispute.expected_by)}.</p>
        </section>
      ) : t.can_dispute ? (
        <DisputeForm transactionId={t.id} suggested={t.possible_duplicate_of ? "charged_twice" : undefined} />
      ) : (
        t.direction === "debit" && <p className="text-sm text-muted-foreground">This payment can&apos;t be disputed: {t.dispute_note}.</p>
      )}
    </div>
  )
}
