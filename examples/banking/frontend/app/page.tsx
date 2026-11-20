import Link from "next/link"
import { ArrowLeftRightIcon, ArrowRightIcon, BellIcon, CreditCardIcon, PiggyBankIcon, ReceiptIcon } from "lucide-react"

import { CardArt } from "@/components/bank/card-art"
import { ScreenState } from "@/components/bank/screen-state"
import { TxnTable } from "@/components/bank/txn-table"
import { Button } from "@/components/ui/button"
import { bank } from "@/lib/bank"
import { longMonth, rupees, shortDate } from "@/lib/format"
import type { Account, AttentionItem, Card, MonthSummary, MyContext, TxnList } from "@/lib/types"

export default async function HomePage() {
  const [me, { accounts, total_balance }, { cards }, recent, month, { items }] = await Promise.all([
    bank<MyContext>("/api/me"),
    bank<{ accounts: Account[]; total_balance: number }>("/api/accounts"),
    bank<{ cards: Card[] }>("/api/cards"),
    bank<TxnList>("/api/transactions", { query: { limit: 8 } }),
    bank<MonthSummary>("/api/insights/summary"),
    bank<{ items: AttentionItem[] }>("/api/attention"),
  ])
  const credit = cards.find((c) => c.kind === "credit" && c.status !== "blocked")
  const firstName = me.customer.name.split(" ")[0]

  return (
    <div className="flex flex-col gap-8">
      <ScreenState name="accounts" value={{ total_balance, accounts: accounts.map((a) => ({ id: a.id, balance: a.balance })), attention: items.length }} />
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Good to see you, {firstName}</p>
          <h1 className="text-3xl font-semibold tracking-tight tabular-nums sm:text-4xl">{rupees(total_balance)}</h1>
          <p className="text-sm text-muted-foreground">across {accounts.length} accounts</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <Link href="/transfer">
              <ArrowLeftRightIcon /> Send money
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/bills">
              <ReceiptIcon /> Pay bills
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/deposits">
              <PiggyBankIcon /> Open FD
            </Link>
          </Button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {accounts.map((a) => (
          <Link key={a.id} href={`/accounts/${a.id}`} className="group flex flex-col gap-3 rounded-2xl border bg-card p-5 hover:border-primary" data-testid={`account-${a.id}`}>
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{a.name}</span>
              <span className="font-mono text-muted-foreground">{a.number_masked}</span>
            </div>
            <span className="text-2xl font-semibold tabular-nums">{rupees(a.balance)}</span>
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>In this month {rupees(a.money_in_this_month)}</span>
              <span>Out {rupees(a.money_out_this_month)}</span>
            </div>
            {a.holders.length > 1 && <span className="text-xs text-muted-foreground">Joint with {a.holders.slice(1).join(", ")}</span>}
          </Link>
        ))}
        {credit?.statement && (
          <Link href={`/cards/${credit.id}`} className="flex flex-col gap-3 rounded-2xl border bg-card p-5 hover:border-primary">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5 font-medium">
                <CreditCardIcon className="size-4" /> {credit.name}
              </span>
              <span className="font-mono text-muted-foreground">••{credit.last4}</span>
            </div>
            <span className="text-2xl font-semibold tabular-nums">{rupees(credit.outstanding ?? 0)}</span>
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>
                {credit.statement.total_due_now > 0 ? `${rupees(credit.statement.total_due_now)} due ${shortDate(credit.statement.due_date)}` : "Statement paid"}
              </span>
              <span>Available {rupees(credit.available_credit ?? 0)}</span>
            </div>
          </Link>
        )}
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
          <div className="flex items-end justify-between">
            <h2 className="text-xl font-semibold tracking-tight">Recent transactions</h2>
            <Link href="/transactions" className="text-sm text-primary hover:underline">
              See all
            </Link>
          </div>
          <TxnTable transactions={recent.transactions} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          {items.length > 0 && (
            <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
              <span className="flex items-center gap-1.5 text-sm font-medium text-amber-700">
                <BellIcon className="size-4" /> Needs your attention
              </span>
              <ul className="flex flex-col gap-2 text-sm">
                {items.map((item) => (
                  <li key={`${item.kind}-${item.ref}`}>
                    <Link href={item.href} className="hover:underline">
                      {item.text}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <Link href="/insights" className="group flex flex-col gap-3 rounded-2xl border bg-card p-5 hover:border-primary">
            <span className="text-sm font-medium">{longMonth(month.month)} so far</span>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="text-muted-foreground">Income</span>
              <span className="text-right tabular-nums">{rupees(month.income)}</span>
              <span className="text-muted-foreground">Spending</span>
              <span className="text-right tabular-nums">{rupees(month.spending)}</span>
              <span className="text-muted-foreground">Invested</span>
              <span className="text-right tabular-nums">{rupees(month.invested)}</span>
            </div>
            <ul className="flex flex-col gap-1 border-t pt-3 text-xs text-muted-foreground">
              {month.top_categories.slice(0, 4).map((c) => (
                <li key={c.category} className="flex justify-between">
                  <span>{c.category}</span>
                  <span className="tabular-nums">{rupees(c.amount)}</span>
                </li>
              ))}
            </ul>
            <span className="flex items-center gap-1 text-sm font-medium text-primary">
              Insights <ArrowRightIcon className="size-4 transition group-hover:translate-x-0.5" />
            </span>
          </Link>
          <div className="hidden gap-3 sm:grid sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {cards
              .filter((c) => c.status !== "blocked")
              .map((c) => (
                <Link key={c.id} href={`/cards/${c.id}`} aria-label={c.label}>
                  <CardArt card={c} className="max-w-none" />
                </Link>
              ))}
          </div>
        </div>
      </section>
    </div>
  )
}
