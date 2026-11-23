"use client"

import { useRouter } from "next/navigation"

import { useRelayAction } from "@/components/relay/relay-provider"

const DATE = /^\d{4}-\d{2}-\d{2}$/
const PRODUCTS = ["home_loan", "home_improvement", "car_loan", "personal_loan", "education_loan", "gold_loan", "loan_against_fd"]

/**
 * Screen actions available on every page: the assistant works the portal's own screens (statement,
 * transfer form, loan rates) instead of drawing copies of them. Other pages: navigation + page forms.
 */
export function BankActions() {
  const router = useRouter()

  useRelayAction(
    "SHOW_STATEMENT",
    (params) => {
      const q = new URLSearchParams()
      if (params.account) {
        if (!/^(SB|CA)-\d+$/.test(String(params.account).toUpperCase())) throw new Error("account must look like SB-01 or CA-01")
        q.set("account", String(params.account).toUpperCase())
      }
      if (params.last_n) {
        q.set("period", "last")
        q.set("last_n", String(params.last_n))
      } else {
        for (const key of ["from", "to"] as const) {
          const value = params[key]
          if (value && !DATE.test(String(value))) throw new Error(`${key} must look like 2026-10-01`)
          if (value) q.set(key, String(value))
        }
      }
      for (const key of ["direction", "query", "min", "max"] as const) {
        if (params[key] !== undefined && params[key] !== null && params[key] !== "") q.set(key, String(params[key]))
      }
      router.push(`/statement${q.size ? `?${q}` : ""}`)
      return { opened: "/statement", applied: Object.fromEntries(q) }
    },
    {
      description:
        "Show the savings account statement page with these filters (prefer this over drawing a list of transactions). Either last_n or a from/to date range; " +
        "query matches words in the bank's narration (e.g. 'ATM', 'UPI', 'NEFT', 'CHGS', a name in capitals).",
      parameters: {
        type: "object",
        properties: {
          account: { type: "string", description: "SB-01 (main savings, default) or another savings / current account like SB-02, CA-01" },
          from: { type: "string", description: "YYYY-MM-DD" },
          to: { type: "string", description: "YYYY-MM-DD" },
          last_n: { type: "integer", enum: [10, 20, 50, 100] },
          direction: { type: "string", enum: ["debit", "credit"] },
          query: { type: "string", description: "Words in the narration" },
          min: { type: "integer", description: "Minimum amount, ₹" },
          max: { type: "integer", description: "Maximum amount, ₹" },
        },
      },
    },
  )

  useRelayAction(
    "START_TRANSFER",
    (params) => {
      const q = new URLSearchParams()
      if (params.beneficiary_id) q.set("beneficiary", String(params.beneficiary_id).toUpperCase())
      for (const key of ["amount", "mode", "remarks"] as const) {
        if (params[key] !== undefined && params[key] !== null && params[key] !== "") q.set(key, String(params[key]))
      }
      router.push(`/transfers${q.size ? `?${q}` : ""}#transfer`)
      return { opened: "/transfers", filled: Object.fromEntries(q), note: "The page checks the transfer live; the customer ticks the declaration and presses Submit." }
    },
    {
      description: "Open the Funds Transfer page with the form filled in (beneficiary, amount, mode, remarks). Nothing is sent until the customer submits.",
      parameters: {
        type: "object",
        properties: {
          beneficiary_id: { type: "string", description: "Like BEN-03 (list_beneficiaries)" },
          amount: { type: "integer", minimum: 1 },
          mode: { type: "string", enum: ["within_vnb", "imps", "neft", "rtgs"] },
          remarks: { type: "string" },
        },
        required: ["beneficiary_id"],
      },
    },
  )

  useRelayAction(
    "SHOW_LOAN_PRODUCT",
    (params) => {
      const product = String(params.product ?? "")
      if (!PRODUCTS.includes(product)) throw new Error(`product must be one of ${PRODUCTS.join(", ")}`)
      router.push(`/loans?product=${product}#product-${product}`)
      return { opened: "/loans", highlighted: product, note: "Its row in the rate table is highlighted and the Apply form below is set to it." }
    },
    {
      description: "Open the Loans page with one product's row highlighted in the rate table and the Apply for Loan form set to that product.",
      parameters: { type: "object", properties: { product: { type: "string", enum: PRODUCTS } }, required: ["product"] },
    },
  )

  return null
}
