"use server"

/**
 * The site's writes (server actions). Each runs the same bank API endpoint — and so the same rules — as
 * the assistant's side-effecting tool of that name, then refreshes the page. Inventory:
 * examples/national-bank/relay-tools.md.
 */
import { refresh } from "next/cache"

import { read, VnbError, write } from "@/lib/vnb"

export type ActionResult = { ok: boolean; error?: string; fields?: Record<string, string>; message?: string }

// Writes a form on this site may run. Anything else is refused.
const WRITES = new Set([
  "add_beneficiary",
  "delete_beneficiary",
  "transfer_funds",
  "apply_for_loan",
  "prepay_loan",
  "open_fixed_deposit",
  "open_recurring_deposit",
  "close_fixed_deposit",
  "enroll_in_scheme",
  "open_ssy_account",
  "deposit_to_ppf",
  "request_cheque_book",
  "stop_cheque",
  "block_debit_card",
  "update_debit_card_usage",
  "submit_kyc_declaration",
  "raise_complaint",
  "open_account",
  "close_account",
  "transfer_between_own_accounts",
  "set_transfer_limit",
  "add_biller",
  "pay_bill",
  "set_bill_autopay",
  "create_standing_instruction",
  "cancel_standing_instruction",
  "pay_tax",
  "submit_form_15g_15h",
  "invest_in_mutual_fund",
  "redeem_mutual_fund",
  "open_nps_account",
  "contribute_to_nps",
  "apply_for_locker",
  "update_nominee",
  "register_positive_pay",
])

// Checks a form may run while the customer types (nothing changes).
const CHECKS = new Set(["get_transfer_quote", "quote_deposit", "calculate_emi", "get_fd_closure_quote", "get_prepayment_quote", "get_cheque_status"])

const filled = (form: FormData) =>
  Object.fromEntries([...form.entries()].filter(([k, v]) => typeof v === "string" && v.trim() !== "" && !k.startsWith("$") && k !== "agree"))

export async function submitTool(tool: string, _prev: ActionResult | null, form: FormData): Promise<ActionResult> {
  if (!WRITES.has(tool)) return { ok: false, error: "This request is not available." }
  if (form.has("agree") === false && form.get("$needs_agree") === "1") {
    return { ok: false, error: "Please accept the terms and conditions to proceed.", fields: { agree: "required" } }
  }
  const values: Record<string, unknown> = filled(form)
  // Unchecked checkboxes send nothing: say "false" for the ones the form declares.
  for (const name of String(form.get("$booleans") ?? "").split(",").filter(Boolean)) {
    if (!(name in values)) values[name] = "false"
  }
  let message: string | undefined
  try {
    message = (await write<{ message?: string }>(tool, values)).message
  } catch (e) {
    if (e instanceof VnbError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  refresh()
  return { ok: true, message }
}

export async function checkTool<T>(tool: string, values: Record<string, string>): Promise<T | { error: string }> {
  if (!CHECKS.has(tool)) return { error: "not available" }
  try {
    return await read<T>(tool, values)
  } catch (e) {
    if (e instanceof VnbError) return { error: e.message }
    throw e
  }
}
