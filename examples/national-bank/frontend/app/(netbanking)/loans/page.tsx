import { ApplyLoanForm, EmiCalculator } from "@/components/vnb/loan-forms"
import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Empty, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { Deposit, Loan, LoanApplication, LoanProduct } from "@/lib/types"
import { read } from "@/lib/vnb"

type Search = Record<string, string | string[] | undefined>

export default async function LoansPage({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams
  const highlight = Array.isArray(sp.product) ? sp.product[0] : sp.product
  const [{ products, your_cibil }, mine, { deposits }] = await Promise.all([
    read<{ products: LoanProduct[]; your_cibil: number }>("list_loan_products"),
    read<{ loans: Loan[]; applications: LoanApplication[]; monthly_emis: number }>("list_my_loans"),
    read<{ deposits: Deposit[] }>("list_deposits"),
  ])
  const pledgeable = deposits
    .filter((d) => d.kind === "fd" && d.status === "active" && !d.lien)
    .map((d) => ({ id: d.id, label: `${d.id} — ₹${inr(d.current_value, false)} @ ${d.rate}% (matures ${dmy(d.maturity)})` }))
  const active = mine.loans.filter((l) => l.status === "active")
  return (
    <>
      <ScreenState name="loans_page" value={{ highlighted_product: highlight ?? null, my_loans: active.map((l) => l.id) }} />
      <Box title="Retail Loan Products — Interest Rates (w.e.f. 15.10.2026)" help="Rates are linked to the External Benchmark (EBLR) and the applicant's CIBIL score">
        <div className="overflow-x-auto">
          <table className="gv-table">
            <thead>
              <tr>
                <th rowSpan={2}>Scheme</th>
                <th rowSpan={2}>Purpose</th>
                <th colSpan={4} className="text-center">
                  Rate of interest (% p.a.) by CIBIL score
                </th>
                <th rowSpan={2}>Max tenure</th>
                <th rowSpan={2}>Quantum of loan</th>
                <th rowSpan={2}>Processing charges</th>
                <th rowSpan={2}>Prepayment</th>
                <th rowSpan={2}>Security</th>
              </tr>
              <tr>
                <th>800+</th>
                <th>750–799</th>
                <th>700–749</th>
                <th>&lt;700</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.product} id={`product-${p.product}`} className={highlight === p.product ? "gv-highlight" : undefined}>
                  <td>
                    <b>{p.name}</b>
                    <div className="gv-note">Turnaround: {p.turnaround}</div>
                  </td>
                  <td>{p.for.join("; ")}</td>
                  {p.rates_by_cibil ? (
                    Object.values(p.rates_by_cibil).map((r, i) => (
                      <td key={i} className="num">
                        {r.toFixed(2)}
                      </td>
                    ))
                  ) : (
                    <td colSpan={4} className="text-center">
                      Deposit rate + 1.00%
                    </td>
                  )}
                  <td>{p.max_tenure_months ? `${p.max_tenure_months} months` : "Till deposit maturity"}</td>
                  <td>{p.amount}</td>
                  <td>{p.processing_fee}</td>
                  <td>{p.prepayment}</td>
                  <td>{p.collateral}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="gv-note mt-1 list-disc pl-4">
          <li>Your CIBIL score as per last enquiry: {your_cibil}. Final rate is decided at sanction.</li>
          {products.flatMap((p) => p.notes.map((n) => <li key={`${p.product}-${n}`}>{`${p.name}: ${n}`}</li>))}
          <li>GST @18% is applicable on processing charges. Charges are non-refundable. Documentation charges, CERSAI and stamp duty extra as applicable.</li>
          <li>Total EMIs of all loans should not exceed the prescribed share of net monthly income (FOIR). Age at loan closure as per scheme.</li>
        </ul>
      </Box>

      <Box title="My Loan Accounts" id="my-loans" help={`Total EMI per month: ₹${inr(mine.monthly_emis, false)}`}>
        {active.length === 0 ? (
          <Empty>No active loan accounts.</Empty>
        ) : (
          <table className="gv-table">
            <thead>
              <tr>
                <th>Loan A/c</th>
                <th>Scheme</th>
                <th className="num">Sanctioned</th>
                <th className="num">ROI %</th>
                <th className="num">EMI</th>
                <th className="num">Outstanding</th>
                <th>EMIs paid / left</th>
                <th>Next EMI</th>
                <th>Security</th>
              </tr>
            </thead>
            <tbody>
              {active.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.number} ({l.id})
                  </td>
                  <td>{l.name}</td>
                  <td className="num">{inr(l.sanctioned)}</td>
                  <td className="num">{l.rate.toFixed(2)}</td>
                  <td className="num">{inr(l.emi)}</td>
                  <td className="num">{inr(l.outstanding)}</td>
                  <td>
                    {l.emis_paid} / {l.emis_left}
                  </td>
                  <td>{dmy(l.next_emi_date)}</td>
                  <td>{l.vehicle ?? l.security ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {mine.applications.length > 0 && (
          <>
            <div className="mt-2 font-bold text-[#6e1423]">Loan applications</div>
            <table className="gv-table">
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Scheme</th>
                  <th className="num">Amount</th>
                  <th>Tenure</th>
                  <th>Submitted</th>
                  <th>Status</th>
                  <th>Documents to keep ready</th>
                </tr>
              </thead>
              <tbody>
                {mine.applications.map((a) => (
                  <tr key={a.id}>
                    <td>{a.id}</td>
                    <td>{a.name}</td>
                    <td className="num">{inr(a.amount)}</td>
                    <td>{a.tenure_months} m</td>
                    <td>{dmy(a.submitted)}</td>
                    <td>{a.status}</td>
                    <td>{a.documents.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Box>

      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="EMI Calculator" id="emi-calculator">
          <EmiCalculator products={products} />
        </Box>
        <Box title="Loan Prepayment (Part Payment)" id="prepay" help="EMI remains same; tenure reduces">
          <ToolForm tool="prepay_loan" name="Loan prepayment" submitLabel="Prepay" agree="I agree to the prepayment charges, if applicable, as per the scheme.">
            <Row label="Loan Account" required>
              <select name="loan_id" className="gv-input">
                {active.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.id} — {l.name} — O/s ₹{inr(l.outstanding, false)}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Amount (₹)" required hint="Debited from your savings account">
              <input name="amount" type="number" min={1} className="gv-input w-40" />
            </Row>
          </ToolForm>
        </Box>
      </div>

      <Box title="Apply for Loan (Online Application)" id="apply" help="Pre-approved offers, if any, will be shown after login with OTP">
        <ApplyLoanForm products={products} deposits={pledgeable} initialProduct={highlight} key={highlight ?? "none"} />
      </Box>
    </>
  )
}
