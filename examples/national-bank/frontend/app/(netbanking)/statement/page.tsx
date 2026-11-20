import { ScreenState } from "@/components/vnb/screen-state"
import { Box } from "@/components/vnb/ui"
import { dmy, inr, todayIst } from "@/lib/format"
import type { AccountRow, Statement } from "@/lib/types"
import Link from "next/link"
import { read } from "@/lib/vnb"

type Search = Record<string, string | string[] | undefined>
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? ""

/**
 * Account statement, passbook style: cryptic narrations, no categories, no search box worth the name.
 * The filters are a plain GET form (data-relay-ignore: the assistant uses SHOW_STATEMENT instead).
 */
export default async function StatementPage({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams
  const period = one(sp.period) || (sp.last_n ? "last" : "range")
  const account = one(sp.account) || "SB-01"
  const { accounts } = await read<{ accounts: AccountRow[] }>("get_account_summary")
  const own = accounts.filter((a) => /^(SB|CA)-/.test(a.id))
  const number = own.find((a) => a.id === account)?.number ?? account
  const query = {
    account_id: account,
    from_date: period === "range" ? one(sp.from) : "",
    to_date: period === "range" ? one(sp.to) : "",
    last_n: period === "last" ? one(sp.last_n) || "20" : "",
    direction: one(sp.direction),
    query: one(sp.query),
    min_amount: one(sp.min),
    max_amount: one(sp.max),
    category: one(sp.category),
    limit: "200",
  }
  let statement: Statement | null = null
  let error: string | null = null
  try {
    statement = await read<Statement>("get_account_statement", query)
  } catch (e) {
    error = e instanceof Error ? e.message : String(e)
  }
  const today = todayIst()
  return (
    <>
      <ScreenState name="statement_filters" value={Object.fromEntries(Object.entries(query).filter(([k, v]) => v && k !== "limit"))} />
      <Box title="Account Statement" help="My Accounts & Profile › Account Statement">
        <form method="get" action="/statement" data-relay-ignore>
          <table className="gv-form">
            <tbody>
              <tr>
                <td className="gv-label">Select Account</td>
                <td>
                  <select name="account" className="gv-input" defaultValue={account}>
                    {own.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.number} — {a.type} — {a.branch}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
              <tr>
                <td className="gv-label">Select Period</td>
                <td className="space-y-1">
                  <label className="mr-3">
                    <input type="radio" name="period" value="range" defaultChecked={period === "range"} /> By Date Range
                  </label>
                  <label className="mr-3">
                    <input type="radio" name="period" value="last" defaultChecked={period === "last"} /> Last N Transactions
                  </label>
                  <div>
                    From <input type="date" name="from" className="gv-input" defaultValue={one(sp.from)} max={today} /> To{" "}
                    <input type="date" name="to" className="gv-input" defaultValue={one(sp.to)} max={today} /> or last{" "}
                    <select name="last_n" className="gv-input" defaultValue={one(sp.last_n) || "20"}>
                      {[10, 20, 50, 100].map((n) => (
                        <option key={n}>{n}</option>
                      ))}
                    </select>{" "}
                    transactions
                  </div>
                  <div className="gv-note">Statement can be viewed for a maximum period of 6 months. For older statements, visit the branch.</div>
                </td>
              </tr>
              <tr>
                <td className="gv-label">Transaction Type</td>
                <td>
                  <select name="direction" className="gv-input" defaultValue={one(sp.direction)}>
                    <option value="">All</option>
                    <option value="debit">Debit (Withdrawals)</option>
                    <option value="credit">Credit (Deposits)</option>
                  </select>{" "}
                  Amount from <input name="min" className="gv-input w-20" defaultValue={one(sp.min)} /> to <input name="max" className="gv-input w-20" defaultValue={one(sp.max)} />{" "}
                  Narration contains <input name="query" className="gv-input w-32" defaultValue={one(sp.query)} />
                </td>
              </tr>
            </tbody>
          </table>
          <div className="mt-1.5 flex gap-2">
            <button className="gv-btn gv-btn-primary">Go</button>
            <Link href="/statement" className="gv-btn !text-black !no-underline">
              Reset
            </Link>
            <a href={`/statement/download?${new URLSearchParams(Object.entries(query).filter(([, v]) => v) as [string, string][])}`} className="gv-btn !text-black !no-underline" download>
              Download (CSV / Excel)
            </a>
          </div>
        </form>
      </Box>
      {error && <div className="gv-msg-err">{error}</div>}
      {statement && (
        <Box
          title={`Statement of Account No. ${number} ${statement.from_date ? `from ${dmy(statement.from_date)}` : ""} to ${dmy(statement.to_date)}`}
          help={`${statement.count} transaction(s)`}
        >
          <table className="gv-table" data-testid="statement">
            <thead>
              <tr>
                <th>Txn Date</th>
                <th>Value Date</th>
                <th>Description</th>
                <th>Ref No./Cheque No.</th>
                <th className="num">Debit</th>
                <th className="num">Credit</th>
                <th className="num">Balance</th>
              </tr>
            </thead>
            <tbody>
              {statement.transactions.length === 0 && (
                <tr>
                  <td colSpan={7}>No transactions found for the selected criteria.</td>
                </tr>
              )}
              {statement.transactions.map((t) => (
                <tr key={t.id} id={t.id}>
                  <td className="whitespace-nowrap">{dmy(t.date)}</td>
                  <td className="whitespace-nowrap">{dmy(t.date)}</td>
                  <td className="max-w-[380px] break-all">{t.narration}</td>
                  <td className="font-mono text-[10.5px]">{t.ref}</td>
                  <td className="num">{t.debit ? inr(t.debit) : ""}</td>
                  <td className="num">{t.credit ? inr(t.credit) : ""}</td>
                  <td className="num">{inr(t.balance_after)} Cr</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={4} className="font-bold">
                  Total
                </td>
                <td className="num font-bold">{inr(statement.total_debits)}</td>
                <td className="num font-bold">{inr(statement.total_credits)}</td>
                <td />
              </tr>
            </tfoot>
          </table>
          <p className="gv-note mt-1">
            This is a computer-generated statement and does not require a signature. Narrations are as received from the payment system. Please examine the entries and report
            discrepancies within 15 days, failing which the entries shall be deemed correct.
          </p>
        </Box>
      )}
    </>
  )
}
