import Link from "next/link"

import { AccountSelect, transactional } from "@/components/vnb/fields"
import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { TransferForm } from "@/components/vnb/transfer-form"
import { Box, Row } from "@/components/vnb/ui"
import { inr } from "@/lib/format"
import type { AccountRow, Beneficiary, MyContext } from "@/lib/types"
import { read } from "@/lib/vnb"

type Search = Record<string, string | string[] | undefined>
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? ""

export default async function TransfersPage({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams
  const [{ beneficiaries, sent_today, daily_limit }, me, { accounts }] = await Promise.all([
    read<{ beneficiaries: Beneficiary[]; sent_today: number; daily_limit: number }>("list_beneficiaries"),
    read<MyContext>("get_my_context"),
    read<{ accounts: AccountRow[] }>("get_account_summary"),
  ])
  const own = transactional(accounts)
  const initial = { beneficiary_id: one(sp.beneficiary), amount: one(sp.amount), mode: one(sp.mode), remarks: one(sp.remarks) }
  return (
    <>
      <ScreenState name="beneficiaries" value={beneficiaries.map((b) => `${b.id} ${b.name} (${b.nickname}) ${b.status}`)} />
      <div className="gv-msg-info">
        Transaction limit per day for third-party transfers: ₹{inr(daily_limit, false)}. Used today: ₹{inr(sent_today, false)}. A newly added beneficiary is activated after 4
        hours. NEFT / RTGS / IMPS through Internet Banking are free of charge.
      </div>
      <Box title="Funds Transfer — Other Beneficiary (Within VNB / Other Bank)" help="Payments / Transfers › Funds Transfer" id="transfer">
        <TransferForm beneficiaries={beneficiaries} balance={me.savings_balance} initial={initial} key={JSON.stringify(initial)} />
      </Box>
      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Transfer Between Own Accounts" id="own-transfer" help="Instant, free">
          {own.length < 2 ? (
            <p className="gv-note">
              You have only one savings / current account. <Link href="/open-account">Open another account</Link>.
            </p>
          ) : (
            <ToolForm tool="transfer_between_own_accounts" name="Own account transfer" submitLabel="Transfer">
              <Row label="From" required>
                <AccountSelect accounts={accounts} />
              </Row>
              <Row label="To" required>
                <AccountSelect accounts={accounts} name="to_account" defaultValue={own[1].id} />
              </Row>
              <Row label="Amount (₹)" required>
                <input name="amount" type="number" min={1} className="gv-input w-32" />
              </Row>
              <Row label="Remarks">
                <input name="remarks" maxLength={20} className="gv-input w-40" />
              </Row>
            </ToolForm>
          )}
        </Box>
        <Box title="Set Daily Transfer Limit" id="transfer-limit" help={`Current: ₹${inr(daily_limit, false)}`}>
          <ToolForm tool="set_transfer_limit" name="Daily transfer limit" submitLabel="Update Limit" agree="I understand a higher limit takes effect after 4 hours.">
            <Row label="New daily limit (₹)" required hint="₹10,000 to ₹10,00,000 for transfers to beneficiaries. A lower limit protects you from fraud.">
              <input name="daily_limit_amount" type="number" min={10000} max={1000000} className="gv-input w-36" />
            </Row>
          </ToolForm>
        </Box>
      </div>
      <Box title="Manage Beneficiary" id="manage-beneficiary" help={`${beneficiaries.length} registered`}>
        <table className="gv-table">
          <thead>
            <tr>
              <th>Beneficiary Name</th>
              <th>Nick Name</th>
              <th>Account No.</th>
              <th>IFSC</th>
              <th>Bank / Branch</th>
              <th className="num">Limit (₹)</th>
              <th>Status</th>
              <th>Delete</th>
            </tr>
          </thead>
          <tbody>
            {beneficiaries.map((b) => (
              <tr key={b.id}>
                <td>
                  {b.name} <span className="gv-note">({b.id})</span>
                </td>
                <td>{b.nickname}</td>
                <td>{b.account_masked}</td>
                <td>{b.ifsc}</td>
                <td>
                  {b.bank}, {b.branch}
                </td>
                <td className="num">{inr(b.limit, false)}</td>
                <td>{b.status === "active" ? "Active" : <span className="text-[#c00]">Pending activation (from {b.active_from_display})</span>}</td>
                <td>
                  <ToolForm tool="delete_beneficiary" name={`Delete ${b.name}`} submitLabel="Delete" resetLabel={null}>
                    <tr className="hidden">
                      <td>
                        <input type="hidden" name="beneficiary_id" value={b.id} />
                      </td>
                    </tr>
                  </ToolForm>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
      <Box title="Add Beneficiary (Inter-bank / Within VNB)" id="add-beneficiary" help="Beneficiary will be activated 4 hours after adding">
        <ToolForm
          tool="add_beneficiary"
          name="Add beneficiary"
          submitLabel="Add"
          agree="I understand that the bank will credit the account number given by me and will not verify the beneficiary name."
        >
          <Row label="Beneficiary Name" required hint="As in the beneficiary's bank account">
            <input name="name" className="gv-input w-64" />
          </Row>
          <Row label="Account Number" required>
            <input name="account_number" className="gv-input w-56" inputMode="numeric" />
          </Row>
          <Row label="Re-enter Account Number" required>
            <input name="confirm_account_number" className="gv-input w-56" inputMode="numeric" autoComplete="off" />
          </Row>
          <Row label="IFSC Code" required hint="11 characters, 5th is zero, e.g. GGBK0000214. Search IFSC (opens branch directory).">
            <input name="ifsc" className="gv-input w-40 uppercase" maxLength={11} />
          </Row>
          <Row label="Transfer Limit (₹)" hint="Maximum ₹10,00,000">
            <input name="limit" type="number" min={1} max={1000000} defaultValue={100000} className="gv-input w-40" />
          </Row>
          <Row label="Nick Name">
            <input name="nickname" maxLength={30} className="gv-input w-40" />
          </Row>
        </ToolForm>
      </Box>
    </>
  )
}
