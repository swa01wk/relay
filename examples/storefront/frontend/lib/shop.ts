/**
 * The store API client — server-side only (server components and server actions). Every call says
 * which shopper it is for; the browser never talks to the store API directly.
 */
import { connection } from "next/server"

import { currentShopperId } from "@/lib/shopper"

const SHOP_API_URL = (process.env.SHOP_API_URL ?? "http://localhost:8092").replace(/\/$/, "")

export class ShopError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields?: Record<string, string>,
  ) {
    super(message)
  }
}

export async function shop<T>(path: string, init: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}): Promise<T> {
  await connection() // per-shopper data: always rendered at request time, never prerendered
  const url = new URL(`${SHOP_API_URL}${path}`)
  for (const [key, value] of Object.entries(init.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value))
  }
  const headers: Record<string, string> = { "x-shop-user": await currentShopperId() }
  if (process.env.SHOP_API_TOKEN) headers.authorization = `Bearer ${process.env.SHOP_API_TOKEN}`
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
    throw new ShopError(`The store API at ${SHOP_API_URL} is not reachable`, 503)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ShopError(String(body.error ?? body.detail ?? `Store API returned ${res.status}`), res.status, body.fields)
  return body as T
}
