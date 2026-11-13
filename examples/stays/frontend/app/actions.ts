"use server"

/**
 * The site's writes (server actions). Each calls the site API — the same logic the assistant's
 * side-effecting tools run — and refreshes the page. Inventory: examples/stays/relay-tools.md.
 */
import { refresh, revalidatePath } from "next/cache"
import { redirect } from "next/navigation"

import { stays, StaysError } from "@/lib/stays"
import type { CalendarDay, QuoteResult, Trip } from "@/lib/types"

export type ActionResult = { ok: boolean; error?: string; fields?: Record<string, string>; message?: string }

async function run(fn: () => Promise<unknown>): Promise<ActionResult> {
  let message: string | undefined
  try {
    message = ((await fn()) as { message?: string } | undefined)?.message
  } catch (e) {
    if (e instanceof StaysError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  refresh()
  return { ok: true, message }
}

const filled = (form: FormData) =>
  Object.fromEntries([...form.entries()].filter(([k, v]) => typeof v === "string" && v.trim() !== "" && !k.startsWith("$")))

export async function reserveStay(_prev: ActionResult | null, form: FormData): Promise<ActionResult> {
  let trip: Trip
  try {
    trip = (await stays<{ reservation: Trip }>("/api/trips", { method: "POST", body: filled(form) })).reservation
  } catch (e) {
    if (e instanceof StaysError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  revalidatePath("/", "layout")
  redirect(`/trips/${trip.id}?booked=1`)
}

/** Price for the booking panel and the confirm page (no booking). */
export async function quoteStay(listingId: string, query: { check_in: string; check_out: string; adults: number; children: number; infants: number; pets: number }) {
  try {
    return { ok: true as const, result: await stays<QuoteResult>(`/api/listings/${listingId}/quote`, { query }) }
  } catch (e) {
    if (e instanceof StaysError) return { ok: false as const, error: e.message }
    throw e
  }
}

export async function cancelTrip(tripId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => stays(`/api/trips/${tripId}/cancel`, { method: "POST", body: filled(form) }))
}

export async function changeTrip(tripId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => stays(`/api/trips/${tripId}`, { method: "PATCH", body: filled(form) }))
}

export async function messageHost(tripId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => stays(`/api/trips/${tripId}/messages`, { method: "POST", body: { message: form.get("message") } }))
}

export async function writeReview(tripId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => stays(`/api/trips/${tripId}/review`, { method: "POST", body: filled(form) }))
}

export async function toggleSaved(listingId: string, saved: boolean, wishlist?: string) {
  return run(() =>
    saved
      ? stays(`/api/wishlists/items/${listingId}`, { method: "DELETE" })
      : stays("/api/wishlists/items", { method: "POST", body: { listing_id: listingId, wishlist } }),
  )
}

export async function createWishlist(_prev: ActionResult | null, form: FormData) {
  return run(() => stays("/api/wishlists", { method: "POST", body: filled(form) }))
}

/** One month of a home's calendar (availability and nightly price) for the booking panel. */
export async function calendarFor(listingId: string, month: string) {
  try {
    return { ok: true as const, ...(await stays<{ days: CalendarDay[]; min_nights: number }>(`/api/listings/${listingId}/calendar`, { query: { month } })) }
  } catch (e) {
    if (e instanceof StaysError) return { ok: false as const, error: e.message }
    throw e
  }
}
