"use server"

/**
 * The site's writes (server actions). Each calls the booking API — the same logic the assistant's
 * side-effecting tools run — and refreshes the page. Inventory: examples/bus-booking/relay-tools.md.
 */
import { refresh, revalidatePath } from "next/cache"
import { redirect } from "next/navigation"

import { bus, BusError } from "@/lib/bus"
import type { Booking, Quote } from "@/lib/types"

export type ActionResult = { ok: boolean; error?: string; fields?: Record<string, string>; message?: string }

async function run(fn: () => Promise<{ message?: string } | unknown>): Promise<ActionResult> {
  let message: string | undefined
  try {
    const result = (await fn()) as { message?: string } | undefined
    message = result?.message
  } catch (e) {
    if (e instanceof BusError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  refresh()
  return { ok: true, message }
}

/** Only the form's filled-in fields (empty optional passengers are left out). */
const filled = (form: FormData) =>
  Object.fromEntries([...form.entries()].filter(([k, v]) => typeof v === "string" && v.trim() !== "" && !k.startsWith("$")))

export async function bookTickets(_prev: ActionResult | null, form: FormData): Promise<ActionResult> {
  let booking: Booking
  try {
    booking = (await bus<{ booking: Booking }>("/api/bookings", { method: "POST", body: filled(form) })).booking
  } catch (e) {
    if (e instanceof BusError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  revalidatePath("/", "layout") // the header's trip count
  redirect(`/bookings/${booking.id}?booked=1`)
}

export async function cancelBooking(bookingId: string, _prev: ActionResult | null, form: FormData) {
  const seats = form.getAll("seats").map(String)
  return run(() =>
    bus(`/api/bookings/${bookingId}/cancel`, {
      method: "POST",
      body: { reason: form.get("reason"), seats: seats.length ? seats.join(",") : undefined },
    }),
  )
}

export async function changePoints(bookingId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => bus(`/api/bookings/${bookingId}/points`, { method: "PATCH", body: filled(form) }))
}

export async function rescheduleBooking(bookingId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => bus(`/api/bookings/${bookingId}/reschedule`, { method: "POST", body: filled(form) }))
}

export async function rateTrip(bookingId: string, _prev: ActionResult | null, form: FormData) {
  return run(() =>
    bus(`/api/bookings/${bookingId}/rate`, { method: "POST", body: { rating: Number(form.get("rating")), comment: form.get("comment") || undefined } }),
  )
}

export async function addTraveller(_prev: ActionResult | null, form: FormData) {
  return run(() => bus("/api/travellers", { method: "POST", body: filled(form) }))
}

export async function removeTraveller(travellerId: string) {
  return run(() => bus(`/api/travellers/${travellerId}`, { method: "DELETE" }))
}

/** Price check for the checkout summary (no booking): seats + optional offer code. */
export async function quoteFor(tripId: string, seats: string, couponCode: string) {
  try {
    const { quote } = await bus<{ quote: Quote }>(`/api/trips/${tripId}/quote`, {
      query: { seats, coupon_code: couponCode || undefined },
    })
    return { ok: true as const, quote }
  } catch (e) {
    if (e instanceof BusError) return { ok: false as const, error: e.message }
    throw e
  }
}
