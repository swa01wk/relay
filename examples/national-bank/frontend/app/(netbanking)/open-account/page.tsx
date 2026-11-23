import { RelationSelect, transactional } from "@/components/vnb/fields"
import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { inr } from "@/lib/format"
import type { AccountProduct, AccountRow } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function OpenAccountPage() {
  const [{ products, documents }, { accounts }] = await Promise.all([
    read<{ products: AccountProduct[]; documents: string }>("list_account_products"),
    read<{ accounts: AccountRow[] }>("get_account_summary"),
  ])
  const extra = transactional(accounts).filter((a) => a.id !== "SB-01")
  return (
    <>
      <ScreenState name="account_products" value={products.map((p) => `${p.product}: ${p.eligible ? "eligible" : p.why_not}`)} />
      <Box title="Savings / Current Account Products" help="Existing customers can open additional accounts online">
        <div className="overflow-x-auto">
          <table className="gv-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Suitable for</th>
                <th className="num">ROI %</th>
                <th>Minimum balance</th>
                <th>Features</th>
                <th>Charges</th>
                <th>Eligibility</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.product}>
                  <td>
                    <b>{p.name}</b>
                    <div className="gv-note">Holder: {p.holder}</div>
                  </td>
                  <td>{p.for}</td>
                  <td className="num">{p.interest_rate.toFixed(2)}</td>
                  <td>{p.minimum_balance}</td>
                  <td>
                    {p.features.join("; ")}
                    {p.rule && <div className="gv-note">Note: {p.rule}</div>}
                  </td>
                  <td>{p.charges}</td>
                  <td>{p.eligible ? <span className="text-[#2f6b2f]">Eligible</span> : <span className="text-[#a10000]">{p.why_not}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="gv-note mt-1">{documents}</p>
      </Box>
      <Box title="Open an Account Online" id="open">
        <ToolForm
          tool="open_account"
          name="Open account"
          submitLabel="Open Account"
          booleans={["debit_card", "cheque_book"]}
          agree="I have read the terms and conditions, the schedule of charges and the Most Important Terms for the account, and request the bank to open it using my existing KYC."
        >
          <Row label="Account type" required>
            <select name="product" className="gv-input" defaultValue="">
              <option value="">-- Select --</option>
              {products.map((p) => (
                <option key={p.product} value={p.product} disabled={!p.eligible}>
                  {p.name}
                  {p.eligible ? "" : " (not eligible)"}
                </option>
              ))}
            </select>
          </Row>
          <Row label="Opening deposit from SB-01 (₹)" hint="Current account: at least ₹10,000">
            <input name="initial_deposit" type="number" min={0} className="gv-input w-32" />
          </Row>
          <Row label="Nominee name">
            <input name="nominee_name" className="gv-input w-56" />
          </Row>
          <Row label="Nominee relationship">
            <RelationSelect />
          </Row>
          <Row label="Facilities">
            <label className="mr-3">
              <input type="checkbox" name="debit_card" defaultChecked /> Debit card
            </label>
            <label>
              <input type="checkbox" name="cheque_book" /> Cheque book
            </label>
          </Row>
          <Row label="Business name" hint="Only for a current account">
            <input name="business_name" maxLength={80} className="gv-input w-64" />
          </Row>
        </ToolForm>
      </Box>
      <Box title="Close an Additional Account" id="close" help="The main account can be closed only at the branch">
        {extra.length === 0 ? (
          <p className="gv-note">You have no additional savings or current accounts.</p>
        ) : (
          <ToolForm tool="close_account" name="Close account" submitLabel="Close Account" agree="I understand the balance will move to my main account and the debit card will be blocked.">
            <Row label="Account" required>
              <select name="account_id" className="gv-input">
                {extra.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.number} — {a.type} ({a.id}) — ₹{inr(a.balance)}
                  </option>
                ))}
              </select>
            </Row>
          </ToolForm>
        )}
      </Box>
    </>
  )
}
