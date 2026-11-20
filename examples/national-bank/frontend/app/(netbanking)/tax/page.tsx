import { AccountSelect } from "@/components/vnb/fields"
import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { AccountRow, TaxGuide, TaxPayment } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function TaxPage() {
  const [guide, { tax_payments }, { accounts }] = await Promise.all([
    read<TaxGuide>("get_tax_payment_guide"),
    read<{ tax_payments: TaxPayment[] }>("list_tax_payments"),
    read<{ accounts: AccountRow[] }>("get_account_summary"),
  ])
  return (
    <>
      <ScreenState name="tax" value={{ advance_tax_needed: guide.advance_tax_needed, assessment_year: guide.assessment_year }} />
      <div className="gv-msg-info">
        <b>e-Pay Taxes (OLTAS).</b> {guide.advice}
      </div>
      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Advance Tax Due Dates" help={`AY ${guide.assessment_year}`}>
          <table className="gv-table">
            <thead>
              <tr>
                <th>Due date</th>
                <th className="num">Cumulative % of tax</th>
              </tr>
            </thead>
            <tbody>
              {guide.due_dates.map((d) => (
                <tr key={d.due}>
                  <td>{dmy(d.due)}</td>
                  <td className="num">{d.cumulative_percent}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="gv-note mt-1">
            Estimated income from interest this year: ₹{inr(guide.other_income_estimate, false)}; tax on it ≈ ₹{inr(guide.tax_on_other_income, false)} (at your slab
            plus 4% cess).
          </p>
        </Box>
        <Box title="Pay Income Tax — Challan ITNS 280" id="pay-tax">
          <ToolForm tool="pay_tax" name="Pay income tax" submitLabel="Proceed to Pay" agree="I confirm the PAN, assessment year and type of payment. Challans once paid cannot be cancelled by the bank.">
            <Row label="PAN">Registered PAN (masked) will be used</Row>
            <Row label="Type of payment" required>
              <select name="tax_type" className="gv-input">
                <option value="advance_tax">(100) Advance tax</option>
                <option value="self_assessment">(300) Self-assessment tax</option>
              </select>
            </Row>
            <Row label="Assessment year" hint={`e.g. ${guide.assessment_year}`}>
              <input name="assessment_year" defaultValue={guide.assessment_year} className="gv-input w-24" />
            </Row>
            <Row label="Amount (₹)" required>
              <input name="amount" type="number" min={1} className="gv-input w-32" />
            </Row>
            <Row label="Debit account">
              <AccountSelect accounts={accounts} />
            </Row>
          </ToolForm>
        </Box>
      </div>
      <Box title="Form 15G / 15H — Declaration for No TDS" id="form-15g">
        <ToolForm tool="submit_form_15g_15h" name="Form 15G or 15H" submitLabel="Submit Declaration" agree="I declare that the information is true. I am aware that a false declaration is punishable under section 277 of the Income-tax Act.">
          <Row label="Financial year">
            <input name="financial_year" placeholder="2026-27" className="gv-input w-24" />
          </Row>
          <Row label="Estimated total income this year (₹)" hint="All income, including salary and interest">
            <input name="estimated_total_income" type="number" min={0} className="gv-input w-32" />
          </Row>
        </ToolForm>
      </Box>
      <Box title="Challans Paid" help="Quote the CIN in your income-tax return">
        {tax_payments.length === 0 ? (
          <p className="gv-note">No challans paid through Internet Banking.</p>
        ) : (
          <table className="gv-table">
            <thead>
              <tr>
                <th>Paid on</th>
                <th>Type</th>
                <th>AY</th>
                <th className="num">Amount</th>
                <th>BSR code</th>
                <th>CIN</th>
              </tr>
            </thead>
            <tbody>
              {tax_payments.map((t) => (
                <tr key={t.id}>
                  <td>{dmy(t.paid_on)}</td>
                  <td>
                    ({t.minor_head}) {t.label}
                  </td>
                  <td>{t.assessment_year}</td>
                  <td className="num">{inr(t.amount)}</td>
                  <td>{t.bsr_code}</td>
                  <td className="font-mono">{t.cin}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Box>
    </>
  )
}
