/**
 * The site API client — server-side only (server components and server actions). Every call says
 * which guest it is for; the browser never talks to the site API directly.
 */
import { connection } from "next/server"

import { currentGuestId } from "@/lib/guest"

const STAYS_API_URL = (process.env.STAYS_API_URL ?? "http://localhost:8094").replace(/\/$/, "")

export class StaysError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields?: Record<string, string>,
  ) {
    super(message)
  }
}

export async function stays<T>(path: string, init: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}): Promise<T> {
  await connection() // per-guest data: always rendered at request time, never prerendered
  const url = new URL(`${STAYS_API_URL}${path}`)
  for (const [key, value] of Object.entries(init.query ?? {})) {
    if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, String(v)))
    else if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value))
  }
  const headers: Record<string, string> = { "x-stays-user": await currentGuestId() }
  if (process.env.STAYS_API_TOKEN) headers.authorization = `Bearer ${process.env.STAYS_API_TOKEN}`
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
    throw new StaysError(`The site API at ${STAYS_API_URL} is not reachable`, 503)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new StaysError(String(body.error ?? body.detail ?? `Site API returned ${res.status}`), res.status, body.fields)
  return body as T
}

/** Ids of every home in the guest's wishlists (for the hearts on cards). */
export async function savedListingIds(): Promise<Set<string>> {
  const { wishlists } = await stays<{ wishlists: { listings: { id: string }[] }[] }>("/api/wishlists")
  return new Set(wishlists.flatMap((w) => w.listings.map((l) => l.id)))
}
