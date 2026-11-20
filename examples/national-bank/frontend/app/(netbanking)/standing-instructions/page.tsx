import { AccountSelect, transactional } from "@/components/vnb/fields"
import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { AccountRow, Beneficiary, StandingInstruction } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function StandingInstructionsPage() {
  const [{ standing_instructions, monthly_total }, { beneficiaries }, { accounts }] = await Promise.all([
    read<{ standing_instructions: StandingInstruction[]; monthly_total: number }>("list_standing_instructions"),
    read<{ beneficiaries: Beneficiary[] }>("list_beneficiaries"),
    read<{ accounts: AccountRow[] }>("get_account_summary"),
  ])
  const active = standing_instructions.filter((s) => s.status === "active")
  const cancellable = active.filter((s) => !s.system)
  return (
    <>
      <ScreenState name="standing_instructions" value={active.map((s) => `${s.id} ₹${s.amount} to ${s.to_label} on day ${s.day}`)} />
      <Box title="Standing Instructions" help={`Total per month: ₹${inr(monthly_total, false)}`}>
        <table className="gv-table">
          <thead>
            <tr>
              <th>SI No.</th>
              <th>Credit to</th>
              <th className="num">Amount</th>
              <th>Day</th>
              <th>Debit A/c</th>
              <th>From</th>
              <th>Till</th>
              <th>Next execution</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {standing_instructions.map((s) => (
              <tr key={s.id}>
                <td>{s.id}</td>
                <td>
                  {s.to_label}
                  {s.remarks && <div className="gv-note">{s.remarks}</div>}
                </td>
                <td className="num">{inr(s.amount)}</td>
                <td>{s.day}</td>
                <td>{s.from_account}</td>
                <td>{dmy(s.start)}</td>
                <td>{s.end ? dmy(s.end) : "Until cancelled"}</td>
                <td>{dmy(s.next_on)}</td>
                <td>{s.status === "active" ? "Active" : "Cancelled"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="gv-note mt-1">Executed on the given day from the debit account; if the balance is short, the SI fails and a ₹100 + GST charge applies.</p>
      </Box>
      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Create Standing Instruction" id="create">
          <ToolForm tool="create_standing_instruction" name="Create standing instruction" submitLabel="Register SI" agree="I authorise the bank to debit my account every month as instructed.">
            <Row label="Credit to" required>
              <select name="to" className="gv-input max-w-full" defaultValue="">
                <option value="">-- Select --</option>
                <optgroup label="Beneficiaries">
                  {beneficiaries.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} ({b.nickname}) — limit ₹{inr(b.limit, false)}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="My accounts">
                  {transactional(accounts).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.type} ({a.id})
                    </option>
                  ))}
                </optgroup>
              </select>
            </Row>
            <Row label="Amount (₹)" required>
              <input name="amount" type="number" min={1} className="gv-input w-32" />
            </Row>
            <Row label="Day of month" required hint="1 to 28">
              <input name="day_of_month" type="number" min={1} max={28} className="gv-input w-16" />
            </Row>
            <Row label="Start date" hint="Default: tomorrow">
              <input name="start_date" type="date" className="gv-input" />
            </Row>
            <Row label="Number of instalments" hint="Blank = until cancelled">
              <input name="installments" type="number" min={1} max={120} className="gv-input w-16" />
            </Row>
            <Row label="Debit account">
              <AccountSelect accounts={accounts} />
            </Row>
            <Row label="Remarks">
              <input name="remarks" maxLength={30} className="gv-input w-48" />
            </Row>
          </ToolForm>
        </Box>
        <Box title="Cancel Standing Instruction" id="cancel" help="RD instalments stop when the RD is closed">
          <ToolForm tool="cancel_standing_instruction" name="Cancel standing instruction" submitLabel="Cancel SI" agree="I want to stop this standing instruction.">
            <Row label="Standing instruction" required>
              <select name="standing_instruction_id" className="gv-input max-w-full">
                {cancellable.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id} — ₹{inr(s.amount, false)} to {s.to_label} on day {s.day}
                  </option>
                ))}
              </select>
            </Row>
          </ToolForm>
        </Box>
      </div>
    </>
  )
}
