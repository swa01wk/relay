import { CloseDepositButton, OpenDepositForm } from "@/components/bank/deposit-forms"
import { ScreenState } from "@/components/bank/screen-state"
import { Badge } from "@/components/ui/badge"
import { bank } from "@/lib/bank"
import { longDate, mediumDate, rupees, statusLabel } from "@/lib/format"
import type { Account, Deposit, FdRates } from "@/lib/types"

function band(from: number, to: number) {
  const f = (d: number) => (d >= 365 && d % 365 === 0 ? `${d / 365} yr` : d >= 365 ? `${Math.round(d / 30.4)} mo` : `${d} days`)
  return `${f(from)} – ${f(to)}`
}

export default async function DepositsPage() {
  const [{ deposits, total_active }, rates, { accounts }] = await Promise.all([
    bank<{ deposits: Deposit[]; total_active: number }>("/api/deposits"),
    bank<FdRates>("/api/deposits/rates"),
    bank<{ accounts: Account[] }>("/api/accounts"),
  ])
  const closures = await Promise.all(
    deposits
      .filter((d) => d.status === "active")
      .map((d) => bank<{ closure: { payout: number } }>(`/api/deposits/${d.id}/closure`).then((r) => [d.id, r.closure.payout] as const)),
  )
  const payoutNow = Object.fromEntries(closures)
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <ScreenState name="deposits" value={{ total_active, active: deposits.filter((d) => d.status === "active").map((d) => d.id) }} />
      <section className="flex flex-col gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Fixed deposits</h1>
          <p className="text-sm text-muted-foreground">{rupees(total_active)} in active deposits.</p>
        </div>
        <ul className="flex flex-col gap-3">
          {deposits.map((d) => (
            <li key={d.id} className="flex flex-col gap-3 rounded-2xl border bg-card p-5 text-sm" data-testid={`deposit-${d.id}`}>
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">
                  {d.id} · {rupees(d.principal)} at {d.rate}%
                </span>
                <Badge variant={d.status === "active" ? "secondary" : "outline"}>{statusLabel(d.status)}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
                <span className="text-muted-foreground">Opened</span>
                <span className="text-muted-foreground">Matures</span>
                <span className="text-muted-foreground">{d.payout === "quarterly" ? "Every quarter" : "At maturity"}</span>
                <span className="text-muted-foreground">Renews</span>
                <span>{mediumDate(d.opened)}</span>
                <span>{mediumDate(d.maturity_date)}</span>
                <span className="tabular-nums">{d.payout === "quarterly" ? rupees(d.quarterly_interest ?? 0) : rupees(d.maturity_amount)}</span>
                <span>{d.auto_renew ? "Yes" : "No"}</span>
              </div>
              {d.status === "active" ? (
                <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                  <span className="text-muted-foreground">
                    {d.days_to_maturity} days to go{d.interest_paid > 0 && ` · ${rupees(d.interest_paid)} interest paid so far`} · close today for {rupees(payoutNow[d.id] ?? 0)}
                  </span>
                  <CloseDepositButton id={d.id} payout={payoutNow[d.id] ?? 0} />
                </div>
              ) : (
                d.paid_out && <span className="text-muted-foreground">Paid out {rupees(d.paid_out)} on {longDate(d.closed_on ?? d.maturity_date)}</span>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section className="flex flex-col gap-4">
        <OpenDepositForm accounts={accounts.map((a) => ({ id: a.id, label: a.label, balance: a.balance }))} />
        <div className="rounded-2xl border bg-card p-5 text-sm">
          <h2 className="mb-2 font-semibold">Interest rates</h2>
          <table className="w-full">
            <tbody>
              {rates.rates.map((r) => (
                <tr key={r.from_days} className="border-t first:border-0">
                  <td className="py-1.5 text-muted-foreground">{band(r.from_days, r.to_days)}</td>
                  <td className="py-1.5 text-right font-medium tabular-nums">{r.rate.toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted-foreground">Closing early: {rates.premature_penalty}.</p>
        </div>
      </section>
    </div>
  )
}
