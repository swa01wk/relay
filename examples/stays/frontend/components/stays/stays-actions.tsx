"use client"

import { useRouter } from "next/navigation"

import { useRelayAction } from "@/components/relay/relay-provider"
import { AMENITIES, DESTINATIONS, PROPERTY_TYPES, ROOM_TYPES, SORTS, TRIP_STATUSES } from "@/lib/types"

const SCALAR_KEYS = [
  "destination",
  "check_in",
  "check_out",
  "adults",
  "children",
  "infants",
  "pets",
  "min_price",
  "max_price",
  "property_type",
  "room_type",
  "min_bedrooms",
  "instant_book",
  "superhost",
  "min_rating",
  "sort_by",
] as const
const DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Screen actions available on every page (the assistant works the site's own screens instead of
 * drawing copies of them). SET_STAY lives on the listing page's booking panel.
 */
export function StaysActions() {
  const router = useRouter()

  useRelayAction(
    "SEARCH_STAYS",
    (params) => {
      const onSearch = window.location.pathname === "/search"
      const next = new URLSearchParams(onSearch && !params.reset ? window.location.search : "")
      for (const key of SCALAR_KEYS) {
        if (!(key in params)) continue
        const value = params[key]
        if ((key === "check_in" || key === "check_out") && value && !DATE.test(String(value))) throw new Error(`${key} must look like 2026-12-20`)
        if (value === null || value === "" || value === false) next.delete(key)
        else next.set(key, value === true ? "1" : String(value))
      }
      if ("amenities" in params) {
        next.delete("amenities")
        for (const a of (params.amenities as string[] | null) ?? []) next.append("amenities", String(a))
      }
      if (Boolean(next.get("check_in")) !== Boolean(next.get("check_out"))) throw new Error("give both check_in and check_out (or neither)")
      router.push(`/search${next.size ? `?${next}` : ""}`)
      return { applied: Object.fromEntries(next), amenities: next.getAll("amenities"), page: "/search" }
    },
    {
      description:
        "Show the site's search results: destination, dates, guests, filters and sort (always prefer this over drawing a list of homes). On the search page it keeps what is applied unless given or reset is true; null clears one filter. With dates only homes free for those nights show, with their stay total.",
      parameters: {
        type: "object",
        properties: {
          destination: {
            type: ["string", "null"],
            description: `${Object.values(DESTINATIONS).join(", ")}; or a state (Kerala, Rajasthan…) or kind (beach, mountains, countryside, lakes, city)`,
          },
          check_in: { type: ["string", "null"], description: "YYYY-MM-DD" },
          check_out: { type: ["string", "null"], description: "YYYY-MM-DD" },
          adults: { type: ["integer", "null"], minimum: 1 },
          children: { type: ["integer", "null"], minimum: 0 },
          infants: { type: ["integer", "null"], minimum: 0 },
          pets: { type: ["integer", "null"], minimum: 0, maximum: 2 },
          min_price: { type: ["integer", "null"], description: "Per night, ₹" },
          max_price: { type: ["integer", "null"], description: "Per night, ₹" },
          property_type: { type: ["string", "null"], enum: [...Object.keys(PROPERTY_TYPES), null] },
          room_type: { type: ["string", "null"], enum: [...Object.keys(ROOM_TYPES), null] },
          min_bedrooms: { type: ["integer", "null"], minimum: 1 },
          amenities: { type: ["array", "null"], items: { type: "string", enum: Object.keys(AMENITIES) }, description: "All required" },
          instant_book: { type: ["boolean", "null"] },
          superhost: { type: ["boolean", "null"] },
          min_rating: { type: ["number", "null"] },
          sort_by: { type: ["string", "null"], enum: [...Object.keys(SORTS), null] },
          reset: { type: "boolean", description: "Clear everything first" },
        },
      },
    },
  )

  useRelayAction(
    "OPEN_LISTING",
    (params) => {
      const id = String(params.listing_id ?? "").toUpperCase()
      if (!/^LST-\d+$/.test(id)) throw new Error("listing_id must look like LST-1004")
      const q = new URLSearchParams()
      for (const key of ["check_in", "check_out", "adults", "children", "infants", "pets"] as const) {
        if (params[key] !== undefined && params[key] !== null) q.set(key, String(params[key]))
      }
      router.push(`/listings/${id}${q.size ? `?${q}` : ""}`)
      return { opened: id }
    },
    {
      description: "Open a home's page (photos, details, reviews, calendar and booking panel), optionally with dates and guests filled in.",
      parameters: {
        type: "object",
        properties: {
          listing_id: { type: "string", description: "Listing id like LST-1004" },
          check_in: { type: "string" },
          check_out: { type: "string" },
          adults: { type: "integer" },
          children: { type: "integer" },
          infants: { type: "integer" },
          pets: { type: "integer" },
        },
        required: ["listing_id"],
      },
    },
  )

  useRelayAction(
    "OPEN_TRIP",
    (params) => {
      const id = String(params.reservation_id ?? "").toUpperCase()
      if (!/^RSV-\d+$/.test(id)) throw new Error("reservation_id must look like RSV-50004")
      router.push(`/trips/${id}`)
      return { opened: id }
    },
    {
      description: "Open one of the guest's trips (details, check-in info, messages with the host, cancel, change, review).",
      parameters: { type: "object", properties: { reservation_id: { type: "string", description: "Like RSV-50004" } }, required: ["reservation_id"] },
    },
  )

  useRelayAction(
    "FILTER_TRIPS",
    (params) => {
      const status = params.status ? String(params.status) : ""
      router.push(`/trips${status ? `?status=${status}` : ""}`)
      return { status: status || "all" }
    },
    {
      description: "Show the guest's trips, optionally only one status; null shows all.",
      parameters: { type: "object", properties: { status: { type: ["string", "null"], enum: [...TRIP_STATUSES, null] } } },
    },
  )

  useRelayAction(
    "OPEN_WISHLIST",
    (params) => {
      const id = String(params.wishlist_id ?? "")
      if (!id) throw new Error("wishlist_id is required (list_wishlists)")
      router.push(`/wishlists/${encodeURIComponent(id)}`)
      return { opened: id }
    },
    {
      description: "Open one of the guest's wishlists.",
      parameters: { type: "object", properties: { wishlist_id: { type: "string", description: "Wishlist id (list_wishlists)" } }, required: ["wishlist_id"] },
    },
  )

  return null
}
