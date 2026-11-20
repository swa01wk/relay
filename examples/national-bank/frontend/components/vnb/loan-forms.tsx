"use client"

import * as React from "react"

import { checkTool } from "@/app/actions"
import { ToolForm } from "@/components/vnb/tool-form"
import { Row } from "@/components/vnb/ui"
import { inr } from "@/lib/format"
import type { LoanProduct } from "@/lib/types"

type Emi = { emi: number; total_interest: number; total_payable: number; rate: number; yearly_schedule: { year: number; principal: number; interest: number; balance: number }[] }

/** EMI calculator — a page form the assistant can fill; the result shows below as the customer types. */
export function EmiCalculator({ products }: { products: LoanProduct[] }) {
  const [values, setValues] = React.useState({ product: "home_loan", amount: "2500000", tenure_months: "240", rate: "" })
  const [result, setResult] = React.useState<{ key: string; data: Emi | { error: string } } | null>(null)
  const key = JSON.stringify(values)
  React.useEffect(() => {
    if (!values.amount || !values.tenure_months) return
    let live = true
    const id = setTimeout(() => {
      void checkTool<Emi>("calculate_emi", values).then((data) => live && setResult({ key: JSON.stringify(values), data }))
    }, 300)
    return () => {
      live = false
      clearTimeout(id)
    }
  }, [values])
  const change = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setValues((v) => ({ ...v, [e.target.name]: e.target.value }))
  const data = result?.key === key ? result.data : null
  return (
    <form data-relay-form="EMI calculator" aria-label="EMI calculator" onSubmit={(e) => e.preventDefault()}>
      <table className="gv-form">
        <tbody>
          <Row label="Loan Product">
            <select name="product" value={values.product} onChange={change} className="gv-input">
              {products.map((p) => (
                <option key={p.product} value={p.product}>
                  {p.name}
                </option>
              ))}
            </select>
          </Row>
          <Row label="Loan Amount (₹)">
            <input name="amount" type="number" min={1} value={values.amount} onChange={change} className="gv-input w-40" />
          </Row>
          <Row label="Tenure (months)">
            <input name="tenure_months" type="number" min={1} max={360} value={values.tenure_months} onChange={change} className="gv-input w-24" />
          </Row>
          <Row label="Rate of Interest (% p.a.)" hint="Leave blank to use your rate for the product (based on your CIBIL score)">
            <input name="rate" type="number" step="0.01" min={0} max={30} value={values.rate} onChange={change} className="gv-input w-24" />
          </Row>
        </tbody>
      </table>
      {data && "error" in data && <div className="gv-msg-err">{data.error}</div>}
      {data && "emi" in data && (
        <div className="gv-msg-ok" data-testid="emi-result">
          EMI: <b>₹{inr(data.emi, false)}</b> at {data.rate}% · Total interest ₹{inr(data.total_interest, false)} · Total payable ₹{inr(data.total_payable, false)}
        </div>
      )}
    </form>
  )
}

/** Apply for a loan — named like apply_for_loan's parameters. */
export function ApplyLoanForm({ products, deposits, initialProduct }: { products: LoanProduct[]; deposits: { id: string; label: string }[]; initialProduct?: string }) {
  const [product, setProduct] = React.useState(initialProduct ?? "personal_loan")
  return (
    <ToolForm
      tool="apply_for_loan"
      name="Apply for loan"
      submitLabel="Submit Application"
      agree="I declare that the information given is true. I authorise VNB to obtain my credit report from CICs (CIBIL etc.) and to contact me."
    >
      <Row label="Loan Product" required>
        <select name="product" value={product} onChange={(e) => setProduct(e.target.value)} className="gv-input">
          {products.map((p) => (
            <option key={p.product} value={p.product}>
              {p.name}
            </option>
          ))}
        </select>
      </Row>
      <Row label="Loan Amount Required (₹)" required>
        <input name="amount" type="number" min={1} className="gv-input w-40" />
      </Row>
      <Row label="Repayment Tenure (months)" required>
        <input name="tenure_months" type="number" min={1} max={360} className="gv-input w-24" />
      </Row>
      <Row label="Purpose">
        <select name="purpose" className="gv-input" defaultValue="personal_need">
          <option value="personal_need">Any other personal need</option>
          <option value="medical">Medical expenses</option>
          <option value="wedding">Wedding</option>
          <option value="travel">Travel</option>
          <option value="education">Education</option>
          <option value="home_purchase">Buying a house</option>
          <option value="home_construction">Building a house</option>
          <option value="home_renovation">Repairs / renovation</option>
          <option value="vehicle">Buying a car</option>
        </select>
      </Row>
      {product === "loan_against_fd" && (
        <Row label="Deposit to be pledged" required hint="Tax saver deposits can't be pledged">
          <select name="deposit_id" className="gv-input">
            {deposits.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
        </Row>
      )}
      {product === "gold_loan" && (
        <Row label="Gold to be pledged (grams, 22 ct)" required>
          <input name="gold_grams" type="number" min={1} step="0.1" className="gv-input w-24" />
        </Row>
      )}
      {(product === "home_loan" || product === "home_improvement") && (
        <Row label="Property value / estimate (₹)">
          <input name="property_value" type="number" min={1} className="gv-input w-40" />
        </Row>
      )}
      {product === "car_loan" && (
        <Row label="On-road price of the car (₹)">
          <input name="vehicle_price" type="number" min={1} className="gv-input w-40" />
        </Row>
      )}
    </ToolForm>
  )
}
