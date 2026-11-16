/**
 * The booking API client — server-side only (server components and server actions). Every call says
 * which traveller it is for; the browser never talks to the booking API directly.
 */
import { connection } from "next/server"

import { currentTravellerId } from "@/lib/traveller"

const BUS_API_URL = (process.env.BUS_API_URL ?? "http://localhost:8093").replace(/\/$/, "")

export class BusError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields?: Record<string, string>,
  ) {
    super(message)
  }
}

export async function bus<T>(path: string, init: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}): Promise<T> {
  await connection() // per-traveller data: always rendered at request time, never prerendered
  const url = new URL(`${BUS_API_URL}${path}`)
  for (const [key, value] of Object.entries(init.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value))
  }
  const headers: Record<string, string> = { "x-bus-user": await currentTravellerId() }
  if (process.env.BUS_API_TOKEN) headers.authorization = `Bearer ${process.env.BUS_API_TOKEN}`
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
    throw new BusError(`The booking API at ${BUS_API_URL} is not reachable`, 503)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new BusError(String(body.error ?? body.detail ?? `Booking API returned ${res.status}`), res.status, body.fields)
  return body as T
}
