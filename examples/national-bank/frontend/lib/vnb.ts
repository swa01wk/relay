/**
 * The bank API client — server-side only (server components and server actions). The bank API has one
 * endpoint per tool (`GET /api/<read tool>`, `POST /api/<write tool>`), so the site and the assistant
 * run the same rules. Every call says which customer it is for; the browser never calls the bank API.
 */
import { connection } from "next/server"

import { currentCustomerId } from "@/lib/customer"

const VNB_API_URL = (process.env.VNB_API_URL ?? "http://localhost:8096").replace(/\/$/, "")

export class VnbError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields?: Record<string, string>,
  ) {
    super(message)
  }
}

async function call<T>(method: "GET" | "POST", tool: string, values: Record<string, unknown> = {}): Promise<T> {
  await connection() // per-customer data: always rendered at request time, never prerendered
  const url = new URL(`${VNB_API_URL}/api/${tool}`)
  if (method === "GET") {
    for (const [key, value] of Object.entries(values)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value))
    }
  }
  const headers: Record<string, string> = { "x-vnb-user": await currentCustomerId() }
  if (process.env.VNB_API_TOKEN) headers.authorization = `Bearer ${process.env.VNB_API_TOKEN}`
  if (method === "POST") headers["content-type"] = "application/json"
  let res: Response
  try {
    res = await fetch(url, { method, headers, body: method === "POST" ? JSON.stringify(values) : undefined, cache: "no-store" })
  } catch {
    throw new VnbError(`The bank API at ${VNB_API_URL} is not reachable`, 503)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new VnbError(String(body.error ?? body.detail ?? `Bank API returned ${res.status}`), res.status, body.fields)
  return body as T
}

/** Run a read tool (statement, rates, loans…) for the current customer. */
export function read<T>(tool: string, query: Record<string, unknown> = {}): Promise<T> {
  return call<T>("GET", tool, query)
}

/** Run a write tool (transfer, open FD, cheque book…) for the current customer. */
export function write<T>(tool: string, body: Record<string, unknown>): Promise<T> {
  return call<T>("POST", tool, body)
}
