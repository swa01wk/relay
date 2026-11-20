import { AddBillerForm } from "@/components/vnb/biller-forms"
import { AccountSelect } from "@/components/vnb/fields"
import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { AccountRow, Biller } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function BillsPage() {
  const [{ billers, total_due, categories, providers, mobile_plans }, { accounts }] = await Promise.all([
    read<{ billers: Biller[]; total_due: number; categories: Record<string, string>; providers: Record<string, string[]>; mobile_plans: number[] }>("list_billers"),
    read<{ accounts: AccountRow[] }>("get_account_summary"),
  ])
  const postpaid = billers.filter((b) => !b.prepaid)
  return (
    <>
      <ScreenState name="billers" value={billers.map((b) => `${b.id} ${b.nickname || b.provider}: ${b.bill ? `₹${b.bill.amount} due ${b.bill.due}` : "prepaid"}`)} />
      <Box title="Bill Payments (Bharat BillPay — BBPS)" help={`Total due: ₹${inr(total_due, false)}`}>
        <table className="gv-table">
          <thead>
            <tr>
              <th>Biller</th>
              <th>Category</th>
              <th>Consumer No.</th>
              <th className="num">Amount due</th>
              <th>Due date</th>
              <th>Auto pay</th>
              <th>Last paid</th>
            </tr>
          </thead>
          <tbody>
            {billers.map((b) => (
              <tr key={b.id}>
                <td>
                  {b.provider} <span className="gv-note">({b.nickname || b.id})</span>
                </td>
                <td>{b.category_label}</td>
                <td>{b.consumer_number}</td>
                <td className="num">
                  {b.bill
                    ? inr(b.bill.amount)
                    : b.balance !== null && b.balance !== undefined
                      ? `Bal ${inr(b.balance)}`
                      : b.validity_till
                        ? `Plan ₹${b.plan}, valid till ${dmy(b.validity_till)}`
                        : "—"}
                </td>
                <td className={b.days_to_due !== undefined && b.days_to_due <= 3 ? "font-bold text-[#a10000]" : ""}>
                  {b.bill ? dmy(b.bill.due) : "—"}
                  {b.bill?.rebate && <div className="gv-note">{b.bill.rebate}</div>}
                </td>
                <td>{b.autopay ? `On, up to ₹${inr(b.autopay.max_amount, false)}` : "Off"}</td>
                <td>{b.last_paid ? `₹${inr(b.last_paid.amount, false)} on ${dmy(b.last_paid.date)}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Pay Bill / Recharge" id="pay">
          <ToolForm tool="pay_bill" name="Pay bill" submitLabel="Pay Now" agree="I confirm the biller and amount. Payments through BBPS cannot be reversed by the bank.">
            <Row label="Biller" required>
              <select name="biller_id" className="gv-input max-w-full">
                {billers.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.provider} — {b.consumer_number}
                    {b.bill ? ` — due ₹${inr(b.bill.amount, false)}` : ""}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Amount (₹)" hint={`Blank = full amount due. Recharges: enter the amount (mobile plans ₹${mobile_plans.join(", ₹")}).`}>
              <input name="amount" type="number" min={1} className="gv-input w-32" />
            </Row>
            <Row label="Debit account">
              <AccountSelect accounts={accounts} />
            </Row>
          </ToolForm>
        </Box>
        <Box title="Auto Pay (Postpaid Billers)" id="autopay">
          <ToolForm tool="set_bill_autopay" name="Bill autopay" submitLabel="Save" booleans={["enabled"]}>
            <Row label="Biller" required>
              <select name="biller_id" className="gv-input max-w-full">
                {postpaid.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.provider} — {b.consumer_number}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Auto pay">
              <label>
                <input type="checkbox" name="enabled" defaultChecked /> Pay automatically on the due date
              </label>
            </Row>
            <Row label="Pay automatically up to (₹)" hint="Bills above this are sent to you by SMS instead">
              <input name="max_amount" type="number" min={1} className="gv-input w-32" />
            </Row>
            <Row label="Debit account">
              <AccountSelect accounts={accounts} />
            </Row>
          </ToolForm>
        </Box>
      </div>
      <Box title="Register New Biller" id="add-biller">
        <AddBillerForm categories={categories} providers={providers} />
      </Box>
    </>
  )
}
