/**
 * The bank API client — server-side only (server components and server actions). Every call says
 * which customer it is for; the browser never talks to the bank API directly.
 */
import { connection } from "next/server"

import { currentCustomerId } from "@/lib/customer"

const BANK_API_URL = (process.env.BANK_API_URL ?? "http://localhost:8095").replace(/\/$/, "")

export class BankError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields?: Record<string, string>,
  ) {
    super(message)
  }
}

export async function bank<T>(path: string, init: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}): Promise<T> {
  await connection() // per-customer data: always rendered at request time, never prerendered
  const url = new URL(`${BANK_API_URL}${path}`)
  for (const [key, value] of Object.entries(init.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value))
  }
  const headers: Record<string, string> = { "x-bank-user": await currentCustomerId() }
  if (process.env.BANK_API_TOKEN) headers.authorization = `Bearer ${process.env.BANK_API_TOKEN}`
  if (init.body !== undefined) headers["content-type"] = "application/json"
  let res: Response
  try {
    res = await fetch(url, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
    })
  } catch {
    throw new BankError(`The bank API at ${BANK_API_URL} is not reachable`, 503)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new BankError(String(body.error ?? body.detail ?? `Bank API returned ${res.status}`), res.status, body.fields)
  return body as T
}
