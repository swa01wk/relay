import Link from "next/link"

import { CashFlowChart, CategoryChart } from "@/components/bank/charts"
import { ScreenState } from "@/components/bank/screen-state"
import { bank } from "@/lib/bank"
import { longMonth, monthLabel, rupees } from "@/lib/format"
import type { CashFlow, MonthSummary } from "@/lib/types"

type Props = { searchParams: Promise<{ month?: string }> }

export default async function InsightsPage({ searchParams }: Props) {
  const { month } = await searchParams
  const [summary, flow] = await Promise.all([
    bank<MonthSummary>("/api/insights/summary", { query: { month } }),
    bank<CashFlow>("/api/insights/cash-flow", { query: { months: 6 } }),
  ])
  const stats = [
    ["Income", rupees(summary.income)],
    ["Spending", rupees(summary.spending)],
    ["Invested", rupees(summary.invested)],
    ["Saved", summary.savings_rate_pct === null ? rupees(summary.saved) : `${rupees(summary.saved)} (${summary.savings_rate_pct}%)`],
  ]
  return (
    <div className="flex flex-col gap-8">
      <ScreenState name="insights" value={{ month: summary.month, spending: summary.spending, income: summary.income }} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Insights — {longMonth(summary.month)}</h1>
          <p className="text-sm text-muted-foreground">
            {summary.partial_month
              ? `So far this month — last month you spent ${rupees(summary.spending_last_month)}.`
              : summary.change_vs_last_month_pct !== null &&
                `Spending is ${Math.abs(summary.change_vs_last_month_pct)}% ${summary.change_vs_last_month_pct >= 0 ? "higher" : "lower"} than last month (${rupees(summary.spending_last_month)}).`}
          </p>
        </div>
        <nav className="flex flex-wrap gap-1" aria-label="Month">
          {flow.months.map((m) => (
            <Link
              key={m.month}
              href={`/insights?month=${m.month}`}
              aria-current={m.month === summary.month ? "page" : undefined}
              className={m.month === summary.month ? "rounded-full bg-primary px-3 py-1 text-sm text-primary-foreground" : "rounded-full border px-3 py-1 text-sm hover:border-foreground"}
            >
              {monthLabel(m.month)}
            </Link>
          ))}
        </nav>
      </div>
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map(([k, v]) => (
          <div key={k} className="rounded-2xl border bg-card p-4">
            <p className="text-sm text-muted-foreground">{k}</p>
            <p className="text-xl font-semibold tabular-nums">{v}</p>
          </div>
        ))}
      </section>
      <section className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Spending by category</h2>
          <CategoryChart rows={summary.top_categories.map((c) => ({ category: c.category, amount: c.amount }))} />
        </div>
        <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Top merchants</h2>
          <ul className="flex flex-col gap-2 text-sm">
            {summary.top_merchants.map((m) => (
              <li key={m.merchant} className="flex justify-between">
                <Link href={`/transactions?query=${encodeURIComponent(m.merchant)}&from=${summary.month}-01`} className="hover:underline">
                  {m.merchant}
                </Link>
                <span className="tabular-nums">{rupees(m.amount)}</span>
              </li>
            ))}
          </ul>
          {summary.biggest_expense && (
            <p className="mt-auto border-t pt-3 text-sm text-muted-foreground">
              Biggest one-off:{" "}
              <Link href={`/transactions/${summary.biggest_expense.id}`} className="text-foreground hover:underline">
                {summary.biggest_expense.description}, {rupees(summary.biggest_expense.amount)}
              </Link>
            </p>
          )}
        </div>
      </section>
      <section className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
        <h2 className="font-semibold">Six months of cash flow</h2>
        <CashFlowChart months={flow.months} />
        <p className="text-xs text-muted-foreground">Transfers between your own accounts and credit card bill payments are left out.</p>
      </section>
    </div>
  )
}
