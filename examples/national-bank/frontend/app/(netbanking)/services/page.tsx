import Link from "next/link"

import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Empty, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { Card, InterestCertificate, MyContext, ServiceRequest } from "@/lib/types"
import { read } from "@/lib/vnb"

type Search = Record<string, string | string[] | undefined>

export default async function ServicesPage({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams
  const fy = (Array.isArray(sp.fy) ? sp.fy[0] : sp.fy) ?? ""
  const cheque = (Array.isArray(sp.cheque) ? sp.cheque[0] : sp.cheque) ?? ""
  const chequeStatus = cheque
    ? await read<{ cheque_number: number; account_id: string; status: string }>("get_cheque_status", { cheque_number: cheque }).catch((e: unknown) => ({
        error: e instanceof Error ? e.message : String(e),
      }))
    : null
  const [me, { card, replacement }, { requests }, certificate] = await Promise.all([
    read<MyContext>("get_my_context"),
    read<{ card: Card; replacement: Card | null }>("get_debit_card"),
    read<{ requests: ServiceRequest[] }>("list_service_requests"),
    read<InterestCertificate>("get_interest_certificate", { financial_year: fy }),
  ])
  const thisFy = Number(me.today.slice(0, 4)) - (Number(me.today.slice(5, 7)) < 4 ? 1 : 0)
  const fys = [thisFy, thisFy - 1].map((y) => `${y}-${String(y + 1).slice(2)}`)
  return (
    <>
      <ScreenState name="services" value={{ kyc: me.kyc.status, debit_card: card.status, open_requests: requests.filter((r) => r.status !== "Completed").length }} />
      <Box title="Re-KYC — Self Declaration" id="re-kyc" help={`KYC status: ${me.kyc.status}`}>
        {me.kyc.overdue ? (
          <div className="gv-msg-err">
            Your periodic KYC update was due on {dmy(me.kyc.due_date)} (last updated {dmy(me.kyc.last_updated)}). Please submit the declaration to avoid restrictions on
            your account{me.kyc.restriction_date ? ` from ${dmy(me.kyc.restriction_date)}` : ""}.
          </div>
        ) : (
          <div className="gv-msg-ok">KYC up to date. Next due {dmy(me.kyc.due_date)}.</div>
        )}
        <ToolForm
          tool="submit_kyc_declaration"
          name="Re-KYC self declaration"
          submitLabel="Submit Declaration"
          booleans={["address_changed"]}
          agree="I hereby declare that there is no change in my KYC information (name, identity, PAN) already furnished to the bank, except the address given below, if any."
        >
          <Row label="Registered Address">{me.customer.address}</Row>
          <Row label="Change in address?">
            <label>
              <input type="checkbox" name="address_changed" /> Yes, my address has changed
            </label>
          </Row>
          <Row label="New Address" hint="Only if changed. Submit proof of the new address at any branch within 90 days.">
            <textarea name="new_address" rows={2} maxLength={200} className="gv-input w-full max-w-md" />
          </Row>
        </ToolForm>
      </Box>

      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Cheque Book Request" id="cheque-book" help="First 10 leaves per year free">
          <ToolForm tool="request_cheque_book" name="Cheque book request" submitLabel="Submit" agree="I agree to the charges for cheque leaves beyond the free limit (₹4 per leaf + GST).">
            <Row label="Account">30214457824821 — Savings Account</Row>
            <Row label="Number of leaves" required>
              <select name="leaves" className="gv-input" defaultValue="25">
                {[10, 25, 50, 100].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Deliver to" required>
              <select name="deliver_to" className="gv-input">
                <option value="registered_address">Registered address (Speed Post)</option>
                <option value="branch">Home branch (collect in person)</option>
              </select>
            </Row>
          </ToolForm>
        </Box>
        <Box title="Stop Cheque Payment" id="stop-cheque" help="₹100 + GST per instruction">
          <ToolForm tool="stop_cheque" name="Stop cheque payment" submitLabel="Stop Payment" agree="I agree to the stop payment charges. Stop instruction will not apply to cheques already paid.">
            <Row label="Cheque number (from)" required hint="Your current cheque book: 512301 – 512325">
              <input name="cheque_from" type="number" className="gv-input w-28" />
            </Row>
            <Row label="Cheque number (to)" hint="Leave blank for a single cheque">
              <input name="cheque_to" type="number" className="gv-input w-28" />
            </Row>
            <Row label="Reason" required>
              <select name="reason" className="gv-input">
                <option value="lost">Cheque lost</option>
                <option value="stolen">Cheque stolen</option>
                <option value="wrong_details">Issued with wrong details</option>
                <option value="dispute">Dispute with payee</option>
              </select>
            </Row>
          </ToolForm>
        </Box>
      </div>

      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Positive Pay — Confirm a Cheque Issued" id="positive-pay" help="₹50,000 and above; mandatory from ₹5 lakh">
          <ToolForm tool="register_positive_pay" name="Positive Pay" submitLabel="Confirm Cheque" agree="I confirm I have issued this cheque with exactly these details.">
            <Row label="Cheque number" required>
              <input name="cheque_number" type="number" className="gv-input w-28" />
            </Row>
            <Row label="Cheque date" required>
              <input name="cheque_date" type="date" className="gv-input" />
            </Row>
            <Row label="Amount (₹)" required>
              <input name="amount" type="number" min={50000} className="gv-input w-32" />
            </Row>
            <Row label="Payee name" required hint="As written on the cheque">
              <input name="payee_name" className="gv-input w-56" />
            </Row>
          </ToolForm>
        </Box>
        <Box title="Cheque Status Enquiry" id="cheque-status">
          <form method="get" action="/services#cheque-status" data-relay-ignore>
            Cheque number: <input name="cheque" defaultValue={cheque} className="gv-input w-28" /> <button className="gv-btn">Enquire</button>
          </form>
          {chequeStatus && (
            <div className={"error" in chequeStatus ? "gv-msg-err" : "gv-msg-ok"}>
              {"error" in chequeStatus ? chequeStatus.error : `Cheque ${chequeStatus.cheque_number} (${chequeStatus.account_id}): ${chequeStatus.status}`}
            </div>
          )}
        </Box>
      </div>

      <Box title="ATM / Debit Card Services" id="debit-card">
        <table className="gv-table mb-2">
          <thead>
            <tr>
              <th>Card No.</th>
              <th>Variant</th>
              <th>Status</th>
              <th>Valid thru</th>
              <th className="num">ATM limit / day</th>
              <th className="num">POS + e-com limit / day</th>
              <th>International</th>
            </tr>
          </thead>
          <tbody>
            {[card, ...(replacement ? [replacement] : [])].map((c) => (
              <tr key={c.id}>
                <td>{c.number_masked}</td>
                <td>{c.network}</td>
                <td className={c.status === "active" ? "" : "font-bold text-[#a10000]"}>
                  {c.status.toUpperCase()}
                  {c.expected_by ? ` (by ${dmy(c.expected_by)})` : ""}
                </td>
                <td>{c.expiry}</td>
                <td className="num">{inr(c.atm_daily_limit, false)}</td>
                <td className="num">{inr(c.pos_daily_limit, false)}</td>
                <td>{c.international ? "Enabled" : "Disabled"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="grid gap-2 lg:grid-cols-2">
          <div>
            <div className="mb-1 font-bold text-[#6e1423]">Set usage limits</div>
            <ToolForm tool="update_debit_card_usage" name="Debit card usage limits" submitLabel="Update" booleans={["international"]}>
              <Row label="ATM withdrawal limit / day (₹)" hint="Max ₹1,00,000">
                <input name="atm_daily_limit" type="number" min={0} max={100000} defaultValue={card.atm_daily_limit} className="gv-input w-32" />
              </Row>
              <Row label="POS + e-commerce limit / day (₹)" hint="Max ₹2,00,000">
                <input name="pos_daily_limit" type="number" min={0} max={200000} defaultValue={card.pos_daily_limit} className="gv-input w-32" />
              </Row>
              <Row label="International usage">
                <label>
                  <input type="checkbox" name="international" defaultChecked={card.international} /> Enable
                </label>
              </Row>
            </ToolForm>
          </div>
          <div>
            <div className="mb-1 font-bold text-[#a10000]">Block ATM / Debit Card (permanent)</div>
            <ToolForm
              tool="block_debit_card"
              name="Block debit card"
              submitLabel="Block Card"
              booleans={["reissue"]}
              agree="I understand that blocking is permanent and cannot be reversed. Re-issue charges ₹300 + GST apply (nil for a damaged card)."
            >
              <Row label="Reason" required>
                <select name="reason" className="gv-input">
                  <option value="lost">Lost</option>
                  <option value="stolen">Stolen</option>
                  <option value="damaged">Damaged</option>
                  <option value="suspected_misuse">Suspected misuse</option>
                </select>
              </Row>
              <Row label="Re-issue card">
                <label>
                  <input type="checkbox" name="reissue" defaultChecked /> Send a new card to my registered address
                </label>
              </Row>
            </ToolForm>
          </div>
        </div>
      </Box>

      <Box title={`Interest Certificate — FY ${certificate.financial_year}`} id="interest-certificate" help={certificate.period}>
        <form method="get" action="/services#interest-certificate" className="mb-1" data-relay-ignore>
          Financial year:{" "}
          <select name="fy" defaultValue={certificate.financial_year} className="gv-input">
            {fys.map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>{" "}
          <button className="gv-btn">View</button>
        </form>
        <table className="gv-table">
          <thead>
            <tr>
              <th>Account</th>
              <th className="num">Interest (₹)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Savings Account 30214457824821</td>
              <td className="num">{inr(certificate.savings_interest)}</td>
            </tr>
            {certificate.deposit_interest.map((d) => (
              <tr key={d.deposit}>
                <td>
                  {d.deposit} — {d.scheme}
                </td>
                <td className="num">{inr(d.interest)}</td>
              </tr>
            ))}
            <tr>
              <td>
                <b>TDS deducted / due</b>
              </td>
              <td className="num">
                <b>{inr(certificate.tds_deducted_or_due)}</b>
              </td>
            </tr>
          </tbody>
        </table>
        <ul className="gv-note mt-1 list-disc pl-4">
          {certificate.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </Box>

      <Box title="Service Request Status" id="requests" help={<Link href="/complaints" className="!text-[#ffe7b8]">Complaints</Link>}>
        {requests.length === 0 ? (
          <Empty>No service requests found.</Empty>
        ) : (
          <table className="gv-table">
            <thead>
              <tr>
                <th>Request No.</th>
                <th>Description</th>
                <th>Date</th>
                <th>Status</th>
                <th>Expected by</th>
                <th className="num">Charges</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.summary}</td>
                  <td>{dmy(r.raised)}</td>
                  <td>{r.status}</td>
                  <td>{dmy(r.expected_by)}</td>
                  <td className="num">{r.charge ? inr(r.charge) : "Nil"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Box>
    </>
  )
}
