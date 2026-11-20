"use server"

/**
 * The site's writes (server actions). Each calls the bank API — the same logic the assistant's
 * side-effecting tools run — and refreshes the page. Inventory: examples/banking/relay-tools.md.
 */
import { refresh } from "next/cache"

import { bank, BankError } from "@/lib/bank"
import type { FdQuote, TransferQuote } from "@/lib/types"

export type ActionResult = { ok: boolean; error?: string; fields?: Record<string, string>; message?: string }

async function run(fn: () => Promise<unknown>): Promise<ActionResult> {
  let message: string | undefined
  try {
    message = ((await fn()) as { message?: string } | undefined)?.message
  } catch (e) {
    if (e instanceof BankError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  refresh()
  return { ok: true, message }
}

const filled = (form: FormData) =>
  Object.fromEntries([...form.entries()].filter(([k, v]) => typeof v === "string" && v.trim() !== "" && !k.startsWith("$")))

export async function sendMoney(_prev: ActionResult | null, form: FormData): Promise<ActionResult> {
  return run(async () => {
    const res = await bank<{ transfer?: { amount: number; to_label: string; reference: string; arrives: string }; message?: string }>("/api/transfers", {
      method: "POST",
      body: filled(form),
    })
    if (res.transfer) return { message: `Sent ₹${res.transfer.amount.toLocaleString("en-IN")} to ${res.transfer.to_label} (ref ${res.transfer.reference}) — arrives ${res.transfer.arrives}.` }
    return res
  })
}

/** Checks a transfer for the Transfer page (no money moves). */
export async function quoteTransfer(query: { to: string; amount: string; from_account: string; mode?: string }): Promise<TransferQuote> {
  try {
    return await bank<TransferQuote>("/api/transfers/quote", { query })
  } catch (e) {
    if (e instanceof BankError) return { can_send: false, error: e.message, fields: e.fields }
    throw e
  }
}

export async function cancelScheduled(id: string) {
  return run(() => bank(`/api/scheduled/${id}/cancel`, { method: "POST" }))
}

export async function addPayee(_prev: ActionResult | null, form: FormData) {
  return run(() => bank("/api/payees", { method: "POST", body: filled(form) }))
}

export async function removePayee(id: string) {
  return run(() => bank(`/api/payees/${id}`, { method: "DELETE" }))
}

export async function payBill(billerId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => bank(`/api/bills/${billerId}/pay`, { method: "POST", body: filled(form) }))
}

export async function setAutopay(billerId: string, _prev: ActionResult | null, form: FormData) {
  return run(() =>
    bank(`/api/bills/${billerId}/autopay`, { method: "POST", body: { ...filled(form), enabled: form.get("enabled") === "on" ? "true" : "false" } }),
  )
}

export async function lockCard(cardId: string, locked: boolean) {
  return run(() => bank(`/api/cards/${cardId}/lock`, { method: "POST", body: { locked } }))
}

const CONTROLS = ["online", "international", "contactless", "atm"] as const

/** Card controls: every switch on the form is sent (unchecked boxes are absent from FormData). */
export async function updateCardControls(cardId: string, present: string[], _prev: ActionResult | null, form: FormData) {
  const body: Record<string, unknown> = filled(form)
  for (const key of CONTROLS) if (present.includes(key)) body[key] = form.get(key) === "on" ? "true" : "false"
  return run(() => bank(`/api/cards/${cardId}/controls`, { method: "PATCH", body }))
}

export async function reportCard(cardId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => bank(`/api/cards/${cardId}/report`, { method: "POST", body: filled(form) }))
}

export async function payCard(cardId: string, _prev: ActionResult | null, form: FormData) {
  const body = filled(form)
  if (body.pay === "custom") delete body.pay
  else delete body.amount
  return run(() => bank(`/api/cards/${cardId}/pay`, { method: "POST", body }))
}

export async function openDeposit(_prev: ActionResult | null, form: FormData) {
  return run(() => bank("/api/deposits", { method: "POST", body: { ...filled(form), auto_renew: form.get("auto_renew") === "on" ? "true" : "false" } }))
}

export async function quoteDeposit(query: { amount: string; tenure_months: string; payout: string }) {
  try {
    return { ok: true as const, ...(await bank<{ quote: FdQuote }>("/api/deposits/quote", { query })) }
  } catch (e) {
    if (e instanceof BankError) return { ok: false as const, error: e.message }
    throw e
  }
}

export async function closeDeposit(id: string) {
  return run(() => bank(`/api/deposits/${id}/close`, { method: "POST" }))
}

export async function raiseDispute(txnId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => bank(`/api/transactions/${txnId}/dispute`, { method: "POST", body: filled(form) }))
}
