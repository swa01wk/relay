import Link from "next/link"

import { ScreenState } from "@/components/bank/screen-state"
import { TxnFilters } from "@/components/bank/txn-filters"
import { TxnTable } from "@/components/bank/txn-table"
import { bank } from "@/lib/bank"
import { rupees } from "@/lib/format"
import type { Account, Card, TxnList } from "@/lib/types"

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> }
const PAGE = 50

export default async function TransactionsPage({ searchParams }: Props) {
  const sp = await searchParams
  const one = (k: string) => (Array.isArray(sp[k]) ? sp[k]![0] : (sp[k] as string | undefined))
  const page = Math.max(1, Number(one("page") ?? 1) || 1)
  const query = {
    account_id: one("account"),
    query: one("query"),
    category: one("category"),
    direction: one("direction"),
    channel: one("channel"),
    from_date: one("from"),
    to_date: one("to"),
    min_amount: one("min"),
    max_amount: one("max"),
    sort_by: one("sort") === "amount" ? "amount" : "date",
    limit: PAGE,
    offset: (page - 1) * PAGE,
  }
  const [list, { accounts }, { cards }] = await Promise.all([
    bank<TxnList>("/api/transactions", { query }).catch((e: Error) => ({ error: e.message })),
    bank<{ accounts: Account[] }>("/api/accounts"),
    bank<{ cards: Card[] }>("/api/cards"),
  ])
  const options = [...accounts.map((a) => ({ id: a.id, label: a.label })), ...cards.filter((c) => c.kind === "credit" && !c.replaces).map((c) => ({ id: c.id, label: c.label }))]
  const next = new URLSearchParams(Object.entries(sp).flatMap(([k, v]) => (typeof v === "string" && k !== "page" ? [[k, v]] : [])))

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Transactions</h1>
        <p className="text-sm text-muted-foreground">The last six months across your accounts and credit card.</p>
      </div>
      <TxnFilters accounts={options} />
      {"error" in list ? (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{list.error}</p>
      ) : (
        <>
          <ScreenState name="statement" value={{ filters: query, total: list.total, money_in: list.money_in, money_out: list.money_out }} />
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm" data-testid="statement-totals">
            <span>
              <span className="font-medium tabular-nums">{list.total}</span> transactions
            </span>
            <span>
              In <span className="font-medium text-emerald-700 tabular-nums">{rupees(list.money_in)}</span>
            </span>
            <span>
              Out <span className="font-medium tabular-nums">{rupees(list.money_out)}</span>
            </span>
          </div>
          <TxnTable transactions={list.transactions} showBalance={Boolean(query.account_id && query.account_id.startsWith("ACC"))} />
          {list.total > PAGE && (
            <nav className="flex items-center justify-between text-sm" aria-label="Pages">
              {page > 1 ? <Link href={`/transactions?${new URLSearchParams([...next, ["page", String(page - 1)]])}`} className="text-primary hover:underline">← Newer</Link> : <span />}
              <span className="text-muted-foreground">
                Page {page} of {Math.ceil(list.total / PAGE)}
              </span>
              {page * PAGE < list.total ? <Link href={`/transactions?${new URLSearchParams([...next, ["page", String(page + 1)]])}`} className="text-primary hover:underline">Older →</Link> : <span />}
            </nav>
          )}
        </>
      )}
    </div>
  )
}
