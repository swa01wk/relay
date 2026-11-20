import Link from "next/link"

import { ScreenState } from "@/components/vnb/screen-state"
import { Box, New } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { AccountRow, MyContext, Statement } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function AccountSummary() {
  const [me, summary, recent] = await Promise.all([
    read<MyContext>("get_my_context"),
    read<{ accounts: AccountRow[]; as_of: string }>("get_account_summary"),
    read<Statement>("get_account_statement", { last_n: 5 }),
  ])
  const groups: [string, (a: AccountRow) => boolean][] = [
    ["Transaction Accounts", (a) => a.id.startsWith("SB")],
    ["Deposit Accounts", (a) => /^(FD|RD|PPF|SSY)/.test(a.id)],
    ["Loan Accounts", (a) => a.id.startsWith("LN")],
  ]
  return (
    <>
      <ScreenState name="account_summary" value={{ accounts: summary.accounts.map((a) => `${a.id} ${a.type} ${a.balance}`) }} />
      {me.alerts.length > 0 && (
        <div className="gv-msg-info">
          <b>Important messages for you ({me.alerts.length}) <New /></b>
          <ol className="mt-1 list-decimal pl-5">
            {me.alerts.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ol>
          {me.kyc.overdue && (
            <p className="mt-1">
              Please complete Re-KYC at <Link href="/services#re-kyc">e-Services › Re-KYC Self Declaration</Link>.
            </p>
          )}
        </div>
      )}
      <Box title="Account Summary" help={`Balances as on ${summary.as_of}`}>
        {groups.map(([title, match]) => {
          const rows = summary.accounts.filter(match)
          if (!rows.length) return null
          return (
            <div key={title} className="mb-3">
              <div className="mb-1 text-[12px] font-bold text-[#6e1423]">{title}</div>
              <table className="gv-table">
                <thead>
                  <tr>
                    <th>Account No.</th>
                    <th>Account Type</th>
                    <th>Branch / Details</th>
                    <th className="num">Balance (INR)</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((a) => (
                    <tr key={a.id}>
                      <td>
                        {a.number} <span className="gv-note">({a.id})</span>
                      </td>
                      <td>{a.type}</td>
                      <td>
                        {[
                          a.branch,
                          a.rate !== undefined && `ROI ${a.rate}%`,
                          a.maturity && `Maturity ${dmy(a.maturity)}`,
                          a.emi !== undefined && `EMI ₹${inr(a.emi, false)} due ${dmy(a.next_emi_date)}`,
                          a.lien ? `Lien ₹${inr(a.lien, false)}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </td>
                      <td className="num">
                        {inr(Math.abs(a.balance))} {a.balance < 0 ? "Dr" : "Cr"}
                      </td>
                      <td>
                        {a.id === "SB-01" ? (
                          <Link href="/statement">Click here for statement</Link>
                        ) : a.id.startsWith("LN") ? (
                          <Link href="/loans#my-loans">Details</Link>
                        ) : a.id.startsWith("PPF") || a.id.startsWith("SSY") ? (
                          <Link href="/schemes#ppf">Details</Link>
                        ) : (
                          <Link href="/deposits">Details</Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
        <p className="gv-note">
          The balance shown includes uncleared funds, if any. Balance in deposit accounts includes interest accrued up to date. For the exact maturity value, contact your
          branch.
        </p>
      </Box>
      <Box title="Last 5 Transactions — Savings Account" help={<Link href="/statement" className="!text-[#ffe7b8]">View full statement</Link>}>
        <table className="gv-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th className="num">Debit</th>
              <th className="num">Credit</th>
              <th className="num">Balance</th>
            </tr>
          </thead>
          <tbody>
            {recent.transactions.map((t) => (
              <tr key={t.id}>
                <td>{dmy(t.date)}</td>
                <td className="break-all">{t.narration}</td>
                <td className="num">{t.debit ? inr(t.debit) : ""}</td>
                <td className="num">{t.credit ? inr(t.credit) : ""}</td>
                <td className="num">{inr(t.balance_after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
    </>
  )
}
