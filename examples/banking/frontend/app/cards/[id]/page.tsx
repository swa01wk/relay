import Link from "next/link"
import { notFound } from "next/navigation"

import { CardArt } from "@/components/bank/card-art"
import { CardControlsForm, LockButton, PayCardForm, ReportCardForm } from "@/components/bank/card-panel"
import { ScreenState } from "@/components/bank/screen-state"
import { TxnTable } from "@/components/bank/txn-table"
import { bank, BankError } from "@/lib/bank"
import { longDate, rupees, shortDate, statusLabel } from "@/lib/format"
import type { Account, Card } from "@/lib/types"

type Props = { params: Promise<{ id: string }> }

export default async function CardPage({ params }: Props) {
  const { id } = await params
  let card: Card
  try {
    card = (await bank<{ card: Card }>(`/api/cards/${id}`)).card
  } catch (e) {
    if (e instanceof BankError && e.status === 404) notFound()
    throw e
  }
  const { accounts } = await bank<{ accounts: Account[] }>("/api/accounts")
  const st = card.statement
  return (
    <div className="flex flex-col gap-8">
      <ScreenState name="card" value={{ id: card.id, kind: card.kind, status: card.status }} />
      <Link href="/cards" className="text-sm text-primary hover:underline">
        ← Cards
      </Link>
      <section className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex flex-col gap-4">
          <CardArt card={card} />
          <div className="flex flex-wrap items-center gap-2">
            <LockButton card={card} />
            <span className="text-sm text-muted-foreground">Status: {statusLabel(card.status)}</span>
          </div>
          {card.status === "blocked" && (
            <p className="text-sm text-muted-foreground">
              Blocked ({card.blocked_reason}).{" "}
              {card.replaced_by && (
                <Link href={`/cards/${card.replaced_by}`} className="text-primary hover:underline">
                  See the replacement
                </Link>
              )}
            </p>
          )}
          {card.status === "on_the_way" && card.arrives_on && <p className="text-sm text-amber-700">Arrives by {longDate(card.arrives_on)}. It works as soon as it arrives.</p>}
          {card.kind === "credit" && st ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-2xl border bg-card p-5 text-sm">
              <dt className="text-muted-foreground">Credit limit</dt>
              <dd className="text-right tabular-nums">{rupees(card.credit_limit ?? 0)}</dd>
              <dt className="text-muted-foreground">Outstanding</dt>
              <dd className="text-right font-medium tabular-nums">{rupees(card.outstanding ?? 0)}</dd>
              <dt className="text-muted-foreground">Available</dt>
              <dd className="text-right tabular-nums">{rupees(card.available_credit ?? 0)}</dd>
              <dt className="text-muted-foreground">Statement {shortDate(st.statement_date)}</dt>
              <dd className="text-right tabular-nums">{rupees(st.statement_balance)}</dd>
              <dt className="text-muted-foreground">Due {shortDate(st.due_date)}</dt>
              <dd className="text-right font-medium tabular-nums">
                {st.total_due_now > 0 ? `${rupees(st.total_due_now)} (min ${rupees(st.minimum_due_now)})` : "Paid"}
              </dd>
              <dt className="text-muted-foreground">Unbilled</dt>
              <dd className="text-right tabular-nums">{rupees(card.unbilled ?? 0)}</dd>
              <dt className="text-muted-foreground">Reward points</dt>
              <dd className="text-right tabular-nums">{(card.reward_points ?? 0).toLocaleString("en-IN")}</dd>
            </dl>
          ) : (
            card.account_label && (
              <p className="rounded-2xl border bg-card p-5 text-sm">
                Spends from <span className="font-medium">{card.account_label}</span> — balance {rupees(card.account_balance ?? 0)}
              </p>
            )
          )}
        </div>
        <div className="flex flex-col gap-4">
          {card.kind === "credit" && card.status !== "blocked" && (
            <PayCardForm card={card} accounts={accounts.map((a) => ({ id: a.id, label: a.label, balance: a.balance }))} />
          )}
          <CardControlsForm card={card} />
          <ReportCardForm card={card} />
        </div>
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold tracking-tight">{card.kind === "credit" ? "Unbilled transactions" : "Recent card payments"}</h2>
        <TxnTable transactions={card.unbilled_transactions ?? card.recent_transactions ?? []} showAccount={false} />
      </section>
    </div>
  )
}
