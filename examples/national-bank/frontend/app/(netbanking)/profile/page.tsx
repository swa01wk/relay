import Link from "next/link"

import { RelationSelect } from "@/components/vnb/fields"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { MyContext, NomineeRow } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function ProfilePage() {
  const [me, { nominees }] = await Promise.all([read<MyContext>("get_my_context"), read<{ nominees: NomineeRow[] }>("list_nominees")])
  const c = me.customer
  const rows: [string, React.ReactNode][] = [
    ["Customer Name", c.name],
    ["CIF Number", c.cif],
    ["Username", c.username],
    ["Date of Birth", `${dmy(c.dob)} (${me.age} years)`],
    ["Registered Mobile", c.mobile],
    ["E-mail", c.email],
    ["Communication Address", c.address],
    ["Home Branch", `${c.branch} (Code ${c.branch_code}), IFSC ${c.ifsc}`],
    ["Occupation", c.occupation],
    ["Net Monthly Income (as declared)", `₹${inr(c.net_monthly_income, false)}`],
    [
      "KYC",
      <span key="kyc" className={me.kyc.overdue ? "font-bold text-[#a10000]" : ""}>
        {me.kyc.status} — last updated {dmy(me.kyc.last_updated)}, due {dmy(me.kyc.due_date)} · <Link href="/services#re-kyc">Update</Link>
      </span>,
    ],
  ]
  return (
    <>
      <Box title="Profile — Personal Details" help="To change mobile number / e-mail, visit the branch">
        <table className="gv-form">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td className="gv-label">{k}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
      <Box title="Nomination Details" id="nominees" help="Each account and deposit has its own nominee">
        <table className="gv-table">
          <thead>
            <tr>
              <th>Account / Deposit</th>
              <th>Type</th>
              <th>Nominee</th>
            </tr>
          </thead>
          <tbody>
            {nominees.map((n) => (
              <tr key={n.account_id}>
                <td>{n.account_id}</td>
                <td>{n.account}</td>
                <td className={n.nominee === "Not registered" ? "font-bold text-[#a10000]" : ""}>{n.nominee}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
      <Box title="Register / Change Nominee" id="update-nominee">
        <ToolForm tool="update_nominee" name="Update nominee" submitLabel="Submit" agree="I nominate the person below to receive the amount in the account in the event of my death (Form DA-1 / DA-2).">
          <Row label="Account / deposit" required>
            <select name="account_id" className="gv-input max-w-full">
              {nominees.map((n) => (
                <option key={n.account_id} value={n.account_id}>
                  {n.account_id} — {n.account}
                </option>
              ))}
            </select>
          </Row>
          <Row label="Nominee name" required>
            <input name="nominee_name" className="gv-input w-56" />
          </Row>
          <Row label="Relationship" required>
            <RelationSelect />
          </Row>
          <Row label="Nominee's date of birth" required>
            <input name="nominee_dob" type="date" className="gv-input" />
          </Row>
          <Row label="Guardian (if nominee is a minor)">
            <input name="guardian_name" className="gv-input w-56" />
          </Row>
        </ToolForm>
      </Box>
      <Box title="Family Details (as per bank records)">
        <table className="gv-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Relationship</th>
              <th>Date of Birth</th>
              <th className="num">Age</th>
            </tr>
          </thead>
          <tbody>
            {me.family.map((f) => (
              <tr key={f.name}>
                <td>{f.name}</td>
                <td className="capitalize">{f.relation}</td>
                <td>{dmy(f.dob)}</td>
                <td className="num">{f.age}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
    </>
  )
}
