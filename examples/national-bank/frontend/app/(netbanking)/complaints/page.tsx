import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Empty, Row } from "@/components/vnb/ui"
import { dmy } from "@/lib/format"
import type { Complaint } from "@/lib/types"
import { read } from "@/lib/vnb"

const CATEGORIES: [string, string][] = [
  ["atm_cash_not_dispensed", "ATM — account debited but cash not dispensed"],
  ["upi_failed_debited", "UPI / IMPS — transaction failed but amount debited"],
  ["wrong_charges", "Charges levied — not understood / not agreed"],
  ["unauthorized_transaction", "Unauthorised / fraudulent transaction"],
  ["card_issue", "ATM / Debit card related"],
  ["loan_issue", "Loan / EMI related"],
  ["kyc_issue", "KYC / account freeze related"],
  ["other", "Others"],
]

export default async function ComplaintsPage() {
  const { complaints } = await read<{ complaints: Complaint[] }>("list_service_requests")
  return (
    <>
      <ScreenState name="complaints" value={complaints.map((c) => `${c.id} ${c.status}`)} />
      <div className="gv-msg-info">
        For unauthorised electronic transactions, report within <b>3 working days</b> for zero liability. Block your card first: e-Services › ATM / Debit Card Services. If
        you are not satisfied with the resolution, you may approach the Principal Nodal Officer and then the RBI Ombudsman (after 30 days).
      </div>
      <Box title="Lodge a Complaint (Customer Grievance)" id="lodge">
        <ToolForm tool="raise_complaint" name="Lodge complaint" submitLabel="Lodge Complaint" agree="I declare that the information furnished above is true.">
          <Row label="Complaint Category" required>
            <select name="category" className="gv-input" defaultValue="">
              <option value="">-- Select --</option>
              {CATEGORIES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </Row>
          <Row label="Transaction reference / ID" hint="From your statement (TXN-…) or the reference number, if about one transaction">
            <input name="transaction_id" className="gv-input w-48" />
          </Row>
          <Row label="Complaint Details" required hint="Minimum 10 characters, maximum 1000">
            <textarea name="description" rows={4} maxLength={1000} className="gv-input w-full max-w-xl" />
          </Row>
        </ToolForm>
      </Box>
      <Box title="Track Complaint Status">
        {complaints.length === 0 ? (
          <Empty>No complaints registered.</Empty>
        ) : (
          <table className="gv-table">
            <thead>
              <tr>
                <th>Complaint No.</th>
                <th>Docket</th>
                <th>Category</th>
                <th>Details</th>
                <th>Txn</th>
                <th>Lodged on</th>
                <th>Status</th>
                <th>Resolution by</th>
              </tr>
            </thead>
            <tbody>
              {complaints.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.docket}</td>
                  <td>{c.category_label}</td>
                  <td>{c.description}</td>
                  <td>{c.transaction_id ?? ""}</td>
                  <td>{dmy(c.raised)}</td>
                  <td>{c.status}</td>
                  <td>{dmy(c.resolve_by)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Box>
    </>
  )
}
