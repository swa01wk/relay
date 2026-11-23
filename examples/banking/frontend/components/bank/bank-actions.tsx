"use client"

import { useRouter } from "next/navigation"

import { useRelayAction } from "@/components/relay/relay-provider"
import { CATEGORIES, CHANNELS } from "@/lib/types"

const FILTER_KEYS = ["account", "query", "category", "direction", "channel", "from", "to", "min", "max", "sort"] as const
const DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Screen actions available on every page: the assistant works the bank's own screens (statement,
 * transfer page, cards) instead of drawing copies of them.
 */
export function BankActions() {
  const router = useRouter()

  useRelayAction(
    "FILTER_TRANSACTIONS",
    (params) => {
      const onPage = window.location.pathname === "/transactions"
      const next = new URLSearchParams(onPage && !params.reset ? window.location.search : "")
      for (const key of FILTER_KEYS) {
        if (!(key in params)) continue
        const value = params[key]
        if ((key === "from" || key === "to") && value && !DATE.test(String(value))) throw new Error(`${key} must look like 2026-10-01`)
        if (value === null || value === "") next.delete(key)
        else next.set(key, String(value))
      }
      router.push(`/transactions${next.size ? `?${next}` : ""}`)
      return { applied: Object.fromEntries(next), page: "/transactions" }
    },
    {
      description:
        "Show the site's statement page with filters (always prefer this over drawing a list of transactions). On that page it keeps what is applied unless given or reset is true; null clears one filter. The page shows the total in and out for the filter.",
      parameters: {
        type: "object",
        properties: {
          account: { type: ["string", "null"], enum: ["ACC-01", "ACC-02", "CRD-02", null], description: "ACC-01 savings, ACC-02 joint, CRD-02 credit card" },
          query: { type: ["string", "null"], description: "Merchant or words in the description" },
          category: { type: ["string", "null"], enum: [...Object.keys(CATEGORIES), null] },
          direction: { type: ["string", "null"], enum: ["debit", "credit", null], description: "debit = money out" },
          channel: { type: ["string", "null"], enum: [...Object.keys(CHANNELS), null] },
          from: { type: ["string", "null"], description: "YYYY-MM-DD" },
          to: { type: ["string", "null"], description: "YYYY-MM-DD" },
          min: { type: ["integer", "null"], description: "Minimum amount, ₹" },
          max: { type: ["integer", "null"], description: "Maximum amount, ₹" },
          sort: { type: ["string", "null"], enum: ["date", "amount", null] },
          reset: { type: "boolean", description: "Clear everything first" },
        },
      },
    },
  )

  useRelayAction(
    "OPEN_ACCOUNT",
    (params) => {
      const id = String(params.account_id ?? "").toUpperCase()
      if (!/^ACC-\d+$/.test(id)) throw new Error("account_id must look like ACC-01")
      router.push(`/accounts/${id}`)
      return { opened: id }
    },
    {
      description: "Open an account's page (balance, account number and IFSC, cards, standing instructions, recent transactions).",
      parameters: { type: "object", properties: { account_id: { type: "string", enum: ["ACC-01", "ACC-02"] } }, required: ["account_id"] },
    },
  )

  useRelayAction(
    "OPEN_TRANSACTION",
    (params) => {
      const id = String(params.transaction_id ?? "").toUpperCase()
      if (!/^TXN-\d+$/.test(id)) throw new Error("transaction_id must look like TXN-100394")
      router.push(`/transactions/${id}`)
      return { opened: id }
    },
    {
      description: "Open one transaction (details, reference, possible duplicate, and the Raise a dispute form).",
      parameters: { type: "object", properties: { transaction_id: { type: "string", description: "Like TXN-100394" } }, required: ["transaction_id"] },
    },
  )

  useRelayAction(
    "OPEN_CARD",
    (params) => {
      const id = String(params.card_id ?? "").toUpperCase()
      if (!/^CRD-\d+$/.test(id)) throw new Error("card_id must look like CRD-01")
      router.push(`/cards/${id}`)
      return { opened: id }
    },
    {
      description: "Open a card's page (lock, controls and limits, report lost; for the credit card also the statement and Pay card bill).",
      parameters: { type: "object", properties: { card_id: { type: "string", description: "CRD-01 debit, CRD-02 credit (or a replacement id from list_cards)" } }, required: ["card_id"] },
    },
  )

  useRelayAction(
    "START_TRANSFER",
    (params) => {
      const q = new URLSearchParams()
      for (const key of ["to", "amount", "from_account", "mode", "note", "transfer_date", "repeat"] as const) {
        if (params[key] !== undefined && params[key] !== null && params[key] !== "") q.set(key, String(params[key]))
      }
      router.push(`/transfer${q.size ? `?${q}` : ""}`)
      return { opened: "/transfer", filled: Object.fromEntries(q), note: "The customer reviews and presses Send; nothing is sent yet." }
    },
    {
      description:
        "Open the Transfer page with the form filled in (payee or own account, amount, note, date, repeat). The page checks limits and shows the mode; only the customer presses Send.",
      parameters: {
        type: "object",
        properties: {
          to: { type: "string", description: "Payee id (PAY-02) or own account (ACC-02)" },
          amount: { type: "integer", minimum: 1 },
          from_account: { type: "string", enum: ["ACC-01", "ACC-02"] },
          mode: { type: "string", enum: ["upi", "imps", "neft"] },
          note: { type: "string" },
          transfer_date: { type: "string", description: "YYYY-MM-DD, for a later date" },
          repeat: { type: "string", enum: ["once", "monthly"] },
        },
      },
    },
  )

  useRelayAction(
    "SHOW_INSIGHTS",
    (params) => {
      const month = params.month ? String(params.month) : ""
      if (month && !/^\d{4}-\d{2}$/.test(month)) throw new Error("month must look like 2026-10")
      router.push(`/insights${month ? `?month=${month}` : ""}`)
      return { opened: "/insights", month: month || "this month" }
    },
    {
      description: "Open the Insights page for a month: income, spending, savings rate, spending by category and top merchants, six-month cash flow.",
      parameters: { type: "object", properties: { month: { type: "string", description: "YYYY-MM; default this month" } } },
    },
  )

  return null
}
