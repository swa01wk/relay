"use client"

import { useRouter } from "next/navigation"

import { useRelayAction } from "@/components/relay/relay-provider"
import { addDays, todayIst } from "@/lib/format"
import { AMENITIES, BOOKING_STATUSES, BUS_TYPES, CITIES, DEPARTURE_WINDOWS, OPERATORS, SORTS } from "@/lib/types"

const FILTER_KEYS = ["ac", "sleeper", "bus_type", "departure_window", "operator_id", "max_fare", "min_rating", "amenity", "sort_by"] as const
const CITY_CODES = Object.keys(CITIES)

/** City code from a code or a name ("Bangalore" → BLR). */
function cityCode(value: unknown): string | null {
  const raw = String(value ?? "").trim()
  if (!raw) return null
  if (CITY_CODES.includes(raw.toUpperCase())) return raw.toUpperCase()
  const aliases: Record<string, string> = { bangalore: "BLR", madras: "CHE", bombay: "MUM", cochin: "COK", mangalore: "MNG", mysore: "MYS", panaji: "GOA", panjim: "GOA" }
  const key = raw.toLowerCase()
  if (aliases[key]) return aliases[key]
  return Object.entries(CITIES).find(([, name]) => name.toLowerCase().startsWith(key))?.[0] ?? null
}

function journeyDate(value: unknown): string | null {
  const raw = String(value ?? "").trim().toLowerCase()
  if (!raw || raw === "today" || raw === "tonight") return todayIst()
  if (raw === "tomorrow") return addDays(todayIst(), 1)
  return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null
}

/**
 * Screen actions available on every page (the assistant works the site's own screens instead of
 * drawing copies of them). SELECT_SEATS lives on the seat map (trip page).
 */
export function BusActions() {
  const router = useRouter()

  useRelayAction(
    "SEARCH_BUSES",
    (params) => {
      const onSearch = window.location.pathname === "/search"
      const next = new URLSearchParams(onSearch && !params.reset ? window.location.search : "")
      for (const [key, value] of [["from", params.from_city], ["to", params.to_city]] as const) {
        if (value === undefined) continue
        const code = cityCode(value)
        if (!code) throw new Error(`unknown city ${String(value)} — one of ${Object.values(CITIES).join(", ")}`)
        next.set(key, code)
      }
      if (params.date !== undefined) {
        const date = journeyDate(params.date)
        if (!date) throw new Error("date must look like 2026-11-20, today or tomorrow")
        next.set("date", date)
      }
      if (!next.get("from") || !next.get("to")) throw new Error("from_city and to_city are needed for a new search")
      if (!next.get("date")) next.set("date", todayIst())
      for (const key of FILTER_KEYS) {
        if (!(key in params)) continue
        const value = params[key]
        if (value === null || value === "") next.delete(key)
        else next.set(key, value === true ? "1" : value === false ? "0" : String(value))
      }
      router.push(`/search?${next}`)
      return { applied: Object.fromEntries(next), page: "/search" }
    },
    {
      description:
        "Show the site's bus search results for a route and date, filtered and sorted (always prefer this over drawing a list of buses). On the search page it keeps the current route, date and filters unless given or reset is true; null clears one filter. Returns what is now applied.",
      parameters: {
        type: "object",
        properties: {
          from_city: { type: "string", description: `City name or code (${Object.entries(CITIES).map(([c, n]) => `${c} ${n}`).join(", ")})` },
          to_city: { type: "string", description: "City name or code" },
          date: { type: "string", description: "YYYY-MM-DD, today or tomorrow" },
          ac: { type: ["boolean", "null"], description: "true AC only, false non-AC only" },
          sleeper: { type: ["boolean", "null"], description: "true sleepers only, false seaters only" },
          bus_type: { type: ["string", "null"], enum: [...Object.keys(BUS_TYPES), null] },
          departure_window: { type: ["string", "null"], enum: [...Object.keys(DEPARTURE_WINDOWS), null], description: "early_morning <6am, morning 6–12, afternoon 12–6pm, night after 6pm" },
          operator_id: { type: ["string", "null"], enum: [...Object.keys(OPERATORS), null], description: Object.entries(OPERATORS).map(([id, n]) => `${id} ${n}`).join(", ") },
          max_fare: { type: ["number", "null"], description: "Rupees" },
          min_rating: { type: ["number", "null"], description: "1–5 stars" },
          amenity: { type: ["string", "null"], enum: [...Object.keys(AMENITIES), null] },
          sort_by: { type: ["string", "null"], enum: [...Object.keys(SORTS), null] },
          reset: { type: "boolean", description: "Clear every filter first" },
        },
      },
    },
  )

  useRelayAction(
    "OPEN_TRIP",
    (params) => {
      const id = String(params.trip_id ?? "").toUpperCase()
      if (!/^SCH-\d+-\d{8}$/.test(id)) throw new Error("trip_id must look like SCH-1042-20261120")
      router.push(`/trips/${id}`)
      return { opened: id }
    },
    {
      description: "Open a bus's seat map (seats, boarding and dropping points, fare). Then SELECT_SEATS can pick seats on it.",
      parameters: {
        type: "object",
        properties: { trip_id: { type: "string", description: "Trip id like SCH-1042-20261120" } },
        required: ["trip_id"],
      },
    },
  )

  useRelayAction(
    "OPEN_BOOKING",
    (params) => {
      const id = String(params.booking_id ?? "").toUpperCase()
      if (!/^BKG-\d+$/.test(id)) throw new Error("booking_id must look like BKG-30004")
      router.push(`/bookings/${id}`)
      return { opened: id }
    },
    {
      description: "Open one of the traveller's bookings (ticket, boarding point, cancel, reschedule, change points, rate).",
      parameters: {
        type: "object",
        properties: { booking_id: { type: "string", description: "Booking id like BKG-30004" } },
        required: ["booking_id"],
      },
    },
  )

  useRelayAction(
    "FILTER_BOOKINGS",
    (params) => {
      const status = params.status ? String(params.status) : ""
      router.push(`/bookings${status ? `?status=${status}` : ""}`)
      return { status: status || "all" }
    },
    {
      description: "Show the traveller's trips, optionally only one status; null shows all.",
      parameters: {
        type: "object",
        properties: { status: { type: ["string", "null"], enum: [...BOOKING_STATUSES, null] } },
      },
    },
  )

  return null
}
