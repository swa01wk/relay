import { CloseFdForm, OpenFdForm, OpenRdForm } from "@/components/vnb/deposit-forms"
import { ScreenState } from "@/components/vnb/screen-state"
import { Box } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { Deposit, DepositRates } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function DepositsPage() {
  const [rates, { deposits, total_current_value }] = await Promise.all([
    read<DepositRates>("get_deposit_rates"),
    read<{ deposits: Deposit[]; total_current_value: number }>("list_deposits"),
  ])
  const active = deposits.filter((d) => d.status === "active")
  const closable = active.filter((d) => d.kind !== "rd").map((d) => ({ id: d.id, label: `${d.id} — ${d.scheme} — ₹${inr(d.principal ?? 0, false)}` }))
  return (
    <>
      <ScreenState name="deposits" value={active.map((d) => `${d.id} ${d.scheme} ${d.rate}% matures ${d.maturity}`)} />
      <div className="grid gap-2 xl:grid-cols-[1.1fr_1fr]">
        <Box title="Interest Rates on Domestic Term Deposits (below ₹3 crore)" help="w.e.f. 15.10.2026, % p.a.">
          <table className="gv-table">
            <thead>
              <tr>
                <th>Tenor</th>
                <th className="num">General public</th>
                <th className="num">Senior citizens</th>
              </tr>
            </thead>
            <tbody>
              {rates.fixed_deposit_slabs.map((s) => (
                <tr key={s.tenure}>
                  <td>{s.tenure}</td>
                  <td className="num">{s.general.toFixed(2)}</td>
                  <td className="num">{s.senior_citizen.toFixed(2)}</td>
                </tr>
              ))}
              <tr>
                <td>
                  <b>{rates.special_scheme.name}</b> (till {dmy(rates.special_scheme.valid_till)})
                </td>
                <td className="num">
                  <b>{rates.special_scheme.rate.toFixed(2)}</b>
                </td>
                <td className="num">
                  <b>{rates.special_scheme.senior_citizen.toFixed(2)}</b>
                </td>
              </tr>
              <tr>
                <td>{rates.tax_saver.name} — {rates.tax_saver.lock_in}</td>
                <td className="num">{rates.tax_saver.rate.toFixed(2)}</td>
                <td className="num">{rates.tax_saver.senior_citizen.toFixed(2)}</td>
              </tr>
              <tr>
                <td>Savings Bank</td>
                <td className="num">{rates.savings_bank.toFixed(2)}</td>
                <td className="num">{rates.savings_bank.toFixed(2)}</td>
              </tr>
              {Object.entries(rates.small_savings).map(([k, s]) => (
                <tr key={k}>
                  <td>{s.name}</td>
                  <td className="num">{s.rate.toFixed(2)}</td>
                  <td className="num">{s.rate.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="gv-note mt-1 list-disc pl-4">
            <li>Premature withdrawal: {rates.premature_closure}.</li>
            <li>TDS: {rates.tds}.</li>
            <li>Compounding quarterly; interest for deposits below 6 months is simple interest. Rates are subject to change without notice.</li>
          </ul>
        </Box>
        <Box title="My Term Deposits / Recurring Deposits" help={`Total: ₹${inr(total_current_value, false)}`}>
          <table className="gv-table">
            <thead>
              <tr>
                <th>A/c No.</th>
                <th>Scheme</th>
                <th className="num">Principal / Instalment</th>
                <th className="num">ROI</th>
                <th>Opened</th>
                <th>Maturity</th>
                <th className="num">Maturity value</th>
                <th>Lien</th>
              </tr>
            </thead>
            <tbody>
              {active.map((d) => (
                <tr key={d.id}>
                  <td>
                    {d.number} ({d.id})
                  </td>
                  <td>{d.scheme}</td>
                  <td className="num">{d.kind === "rd" ? `${inr(d.monthly ?? 0)} p.m.` : inr(d.principal ?? 0)}</td>
                  <td className="num">{d.rate.toFixed(2)}</td>
                  <td>{dmy(d.opened)}</td>
                  <td>{dmy(d.maturity)}</td>
                  <td className="num">{inr(d.maturity_amount)}</td>
                  <td>{d.lien ? `₹${inr(d.lien, false)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Box>
      </div>
      <Box title="Open e-TDR / e-STDR (Fixed Deposit)" id="open-fd" help="Deposit receipt will be available for download after 30 minutes">
        <OpenFdForm />
      </Box>
      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Open e-RD (Recurring Deposit)" id="open-rd">
          <OpenRdForm />
        </Box>
        <Box title="Premature Closure of Term Deposit" id="close-fd" help="Tax saver deposits cannot be closed before 5 years">
          <CloseFdForm deposits={closable} />
        </Box>
      </div>
    </>
  )
}
