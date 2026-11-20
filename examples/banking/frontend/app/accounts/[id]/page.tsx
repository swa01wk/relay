import Link from "next/link"
import { notFound } from "next/navigation"
import { ArrowLeftRightIcon } from "lucide-react"

import { ScreenState } from "@/components/bank/screen-state"
import { TxnTable } from "@/components/bank/txn-table"
import { Button } from "@/components/ui/button"
import { bank, BankError } from "@/lib/bank"
import { longDate, rupees, shortDate } from "@/lib/format"
import type { AccountDetail } from "@/lib/types"

type Props = { params: Promise<{ id: string }> }

export default async function AccountPage({ params }: Props) {
  const { id } = await params
  let account: AccountDetail
  try {
    account = (await bank<{ account: AccountDetail }>(`/api/accounts/${id}`)).account
  } catch (e) {
    if (e instanceof BankError && e.status === 404) notFound()
    throw e
  }
  const details: [string, string][] = [
    ["Account number", account.account_number],
    ["IFSC", account.ifsc],
    ["Branch", account.branch],
    ["Holders", account.holders.join(", ")],
    ["Nominee", account.nominee ?? "None registered"],
    ["Interest", `${account.interest_rate}% a year, paid quarterly`],
    ["Average balance needed", rupees(account.min_balance)],
    ["Opened", longDate(account.opened)],
  ]
  return (
    <div className="flex flex-col gap-8">
      <ScreenState name="account" value={{ id: account.id, balance: account.balance }} />
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">
            {account.name} {account.number_masked}
          </p>
          <h1 className="text-3xl font-semibold tracking-tight tabular-nums">{rupees(account.balance)}</h1>
          {account.below_min_balance && <p className="text-sm text-amber-700">Below the {rupees(account.min_balance)} average balance.</p>}
        </div>
        <Button asChild>
          <Link href={`/transfer?from_account=${account.id}`}>
            <ArrowLeftRightIcon /> Send from this account
          </Link>
        </Button>
      </section>
      <section className="grid gap-6 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
          <div className="flex items-end justify-between">
            <h2 className="text-xl font-semibold tracking-tight">Recent transactions</h2>
            <Link href={`/transactions?account=${account.id}`} className="text-sm text-primary hover:underline">
              Full statement
            </Link>
          </div>
          <TxnTable transactions={account.recent_transactions} showAccount={false} showBalance />
        </div>
        <div className="flex flex-col gap-4">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-2xl border bg-card p-5 text-sm">
            {details.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="text-right font-medium break-all">{v}</dd>
              </div>
            ))}
          </dl>
          {account.cards.length > 0 && (
            <div className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-sm">
              <h2 className="font-medium">Cards</h2>
              {account.cards.map((c) => (
                <Link key={c.id} href={`/cards/${c.id}`} className="flex justify-between hover:underline">
                  <span>
                    {c.name} ••{c.last4}
                  </span>
                  <span className="text-muted-foreground">{c.status.replace(/_/g, " ")}</span>
                </Link>
              ))}
            </div>
          )}
          {account.scheduled_transfers.length > 0 && (
            <div className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-sm">
              <h2 className="font-medium">Standing instructions</h2>
              {account.scheduled_transfers.map((s) => (
                <div key={s.id} className="flex justify-between gap-2">
                  <span>
                    {s.to_label}
                    {s.note ? ` · ${s.note}` : ""}
                  </span>
                  <span className="text-right text-muted-foreground tabular-nums">
                    {rupees(s.amount)} · {s.next_date ? shortDate(s.next_date) : s.status}
                  </span>
                </div>
              ))}
              <Link href="/transfer" className="text-primary hover:underline">
                Manage
              </Link>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
