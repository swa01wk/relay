"use client"

import * as React from "react"

import { checkTool } from "@/app/actions"
import { ToolForm } from "@/components/vnb/tool-form"
import { Row } from "@/components/vnb/ui"
import { inr } from "@/lib/format"
import type { Beneficiary, TransferQuote } from "@/lib/types"

type Initial = Partial<Record<"beneficiary_id" | "amount" | "mode" | "remarks", string>>

/**
 * Funds transfer to a beneficiary. Fields are named like transfer_funds' parameters: the assistant
 * fills this form (or START_TRANSFER opens it filled); the page checks it live; the customer submits.
 */
export function TransferForm({ beneficiaries, balance, initial }: { beneficiaries: Beneficiary[]; balance: number; initial: Initial }) {
  const [values, setValues] = React.useState({ beneficiary_id: initial.beneficiary_id ?? "", amount: initial.amount ?? "", mode: initial.mode ?? "" })
  const [checked, setChecked] = React.useState<{ key: string; quote: TransferQuote } | null>(null)
  const key = JSON.stringify(values)
  const quote = values.beneficiary_id && values.amount && checked?.key === key ? checked.quote : null

  React.useEffect(() => {
    if (!values.beneficiary_id || !values.amount) return
    let live = true
    const id = setTimeout(() => {
      void checkTool<TransferQuote>("get_transfer_quote", { ...values, mode: values.mode }).then((q) => live && setChecked({ key: JSON.stringify(values), quote: q }))
    }, 300)
    return () => {
      live = false
      clearTimeout(id)
    }
  }, [values])

  // Page forms are filled the way typing is, so read every change (including the assistant's) here.
  const change = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setValues((v) => ({ ...v, [e.target.name]: e.target.value }))
  const ben = beneficiaries.find((b) => b.id === values.beneficiary_id)

  return (
    <ToolForm
      tool="transfer_funds"
      name="Funds transfer"
      submitLabel="Submit"
      agree="I confirm the beneficiary details are correct. The bank is not responsible for transfers to a wrong account number entered by me."
    >
      <Row label="Debit Account">
        30214457824821 — Savings Account (Available balance: ₹{inr(balance)})
      </Row>
      <Row label="Select Beneficiary" required>
        <select name="beneficiary_id" value={values.beneficiary_id} onChange={change} className="gv-input w-full max-w-md">
          <option value="">-- Select --</option>
          {beneficiaries.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name} ({b.nickname}) — {b.bank} — {b.account_masked}
              {b.status === "cooling" ? " — NOT YET ACTIVE" : ""}
            </option>
          ))}
        </select>
      </Row>
      <Row label="Amount (₹)" required hint={ben ? `Limit for this beneficiary: ₹${inr(ben.limit, false)}` : undefined}>
        <input name="amount" type="number" min={1} step={1} value={values.amount} onChange={change} className="gv-input w-40" />
      </Row>
      <Row label="Mode of Transfer" hint="Within VNB for VNB accounts. IMPS up to ₹5 lakh (instant). RTGS for ₹2 lakh and above. NEFT for any amount.">
        <select name="mode" value={values.mode} onChange={change} className="gv-input">
          <option value="">-- Auto --</option>
          {ben?.within_vnb ? (
            <option value="within_vnb">Within VNB</option>
          ) : (
            <>
              <option value="imps">IMPS</option>
              <option value="neft">NEFT</option>
              <option value="rtgs">RTGS</option>
            </>
          )}
        </select>
      </Row>
      <Row label="Remarks">
        <input name="remarks" maxLength={30} defaultValue={initial.remarks} className="gv-input w-64" />
      </Row>
      {quote && (
        <tr>
          <td colSpan={2}>
            {quote.can_send ? (
              <div className="gv-msg-ok" data-testid="transfer-check">
                ₹{inr(quote.amount ?? 0, false)} to {quote.beneficiary?.name} by {quote.mode_label} — credited {quote.arrives}. Charges: Nil. Balance after: ₹
                {inr(quote.balance_after ?? 0)}. Today&apos;s limit left after this: ₹{inr(quote.daily_limit_left_after ?? 0, false)}.
              </div>
            ) : (
              <div className="gv-msg-err" data-testid="transfer-check">
                {quote.problems?.length ? quote.problems.join(". ") : quote.error}
              </div>
            )}
          </td>
        </tr>
      )}
    </ToolForm>
  )
}
