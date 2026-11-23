import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { AccountRow, MyContext, Scheme } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function SchemesPage() {
  const [{ schemes, age }, summary, me] = await Promise.all([
    read<{ schemes: Scheme[]; age: number }>("list_government_schemes"),
    read<{ accounts: AccountRow[] }>("get_account_summary"),
    read<MyContext>("get_my_context"),
  ])
  const ppf = summary.accounts.find((a) => a.id === "PPF-01")
  const ssy = summary.accounts.filter((a) => a.id.startsWith("SSY"))
  return (
    <>
      <ScreenState name="schemes" value={schemes.map((s) => `${s.scheme}: ${s.enrolled ? "enrolled" : s.eligible ? "eligible" : "not eligible"}`)} />
      <Box title="Government Sponsored Schemes" help={`Eligibility shown for your age: ${age} years`}>
        <table className="gv-table">
          <thead>
            <tr>
              <th>Scheme</th>
              <th>Type</th>
              <th>Details</th>
              <th className="num">Premium / yr</th>
              <th className="num">Cover</th>
              <th>Your status</th>
            </tr>
          </thead>
          <tbody>
            {schemes.map((s) => (
              <tr key={s.scheme}>
                <td>
                  <b>{s.name}</b>
                </td>
                <td>{s.kind}</td>
                <td>{s.summary}</td>
                <td className="num">{s.premium_per_year ? inr(s.premium_per_year, false) : "—"}</td>
                <td className="num">{s.cover ? inr(s.cover, false) : "—"}</td>
                <td>{s.enrolled ? <b className="text-[#2f6b2f]">Enrolled / Active</b> : s.eligible ? "Eligible — not enrolled" : <span className="text-[#a10000]">{s.why_not ?? "Not eligible"}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="gv-note mt-1">
          Claims under PMJJBY / PMSBY are settled by the insurance company through the branch. APY is not open to persons who are or have been income-tax payers. For SCSS,
          visit the branch with age proof.
        </p>
      </Box>
      <Box title="Enrolment — PMJJBY / PMSBY" id="enrol">
        <ToolForm
          tool="enroll_in_scheme"
          name="Enrol in insurance scheme"
          submitLabel="Enrol"
          agree="I hereby declare that I am in good health and authorise the bank to auto-debit the annual premium from my account every year until I cancel."
        >
          <Row label="Scheme" required>
            <select name="scheme" className="gv-input">
              <option value="pmjjby">PMJJBY — Life cover ₹2 lakh — ₹436 p.a.</option>
              <option value="pmsby">PMSBY — Accident cover ₹2 lakh — ₹20 p.a.</option>
            </select>
          </Row>
          <Row label="Nominee Name" required>
            <input name="nominee_name" className="gv-input w-56" />
          </Row>
          <Row label="Relationship with Nominee" required>
            <select name="nominee_relation" className="gv-input">
              <option value="">-- Select --</option>
              {["wife", "husband", "son", "daughter", "mother", "father", "brother", "sister"].map((r) => (
                <option key={r} value={r}>
                  {r[0].toUpperCase() + r.slice(1)}
                </option>
              ))}
            </select>
          </Row>
        </ToolForm>
      </Box>
      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Sukanya Samriddhi Yojana — Open Account" id="ssy" help="Girl child below 10 years">
          {ssy.length > 0 && (
            <div className="gv-msg-ok">
              {ssy.map((a) => (
                <div key={a.id}>
                  {a.type}: A/c {a.number}, balance ₹{inr(a.balance, false)}, matures {dmy(a.maturity)}
                </div>
              ))}
            </div>
          )}
          <ToolForm tool="open_ssy_account" name="Open Sukanya Samriddhi account" submitLabel="Open Account" agree="I am the natural / legal guardian of the girl child and the details are true.">
            <Row label="Name of girl child" required>
              <input name="girl_name" className="gv-input w-56" />
            </Row>
            <Row label="Date of birth" required hint="Birth certificate to be submitted at the branch within 30 days">
              <input name="girl_dob" type="date" className="gv-input" />
            </Row>
            <Row label="Initial deposit (₹)" required hint="₹250 to ₹1,50,000 per financial year">
              <input name="initial_deposit" type="number" min={250} max={150000} className="gv-input w-32" />
            </Row>
          </ToolForm>
        </Box>
        <Box title="Public Provident Fund — Deposit" id="ppf" help="Max ₹1,50,000 per financial year">
          {ppf && (
            <p className="mb-1">
              PPF A/c {ppf.number}: balance ₹{inr(ppf.balance)} · matures {dmy(ppf.maturity)}. Family on record: {me.family.map((f) => `${f.name} (${f.relation}, ${f.age})`).join(", ")}.
            </p>
          )}
          <ToolForm tool="deposit_to_ppf" name="Deposit to PPF" submitLabel="Deposit" agree="I understand that deposits above ₹1,50,000 in a financial year earn no interest.">
            <Row label="PPF Account">32019985120 (PPF-01)</Row>
            <Row label="Amount (₹)" required hint="Multiples of ₹50, minimum ₹500 a year">
              <input name="amount" type="number" min={50} step={50} className="gv-input w-32" />
            </Row>
          </ToolForm>
        </Box>
      </div>
    </>
  )
}
