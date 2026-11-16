import { Suspense } from "react"
import Link from "next/link"

import { ListingCard } from "@/components/stays/listing-card"
import { ScreenState } from "@/components/stays/screen-state"
import { SearchBar } from "@/components/stays/search-bar"
import { SearchFilters } from "@/components/stays/search-filters"
import { savedListingIds, stays, StaysError } from "@/lib/stays"
import { dateRange, guestsLabel } from "@/lib/format"
import type { SearchResult } from "@/lib/types"

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> }
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)
const many = (v: string | string[] | undefined) => (v === undefined ? [] : Array.isArray(v) ? v : [v])
const bool = (v: string | undefined) => (v === "1" ? true : undefined)

export default async function SearchPage({ searchParams }: Props) {
  const sp = await searchParams
  const query = {
    destination: one(sp.destination),
    check_in: one(sp.check_in),
    check_out: one(sp.check_out),
    adults: one(sp.adults),
    children: one(sp.children),
    infants: one(sp.infants),
    pets: one(sp.pets),
    min_price: one(sp.min_price),
    max_price: one(sp.max_price),
    property_type: one(sp.property_type),
    room_type: one(sp.room_type),
    min_bedrooms: one(sp.min_bedrooms),
    amenities: many(sp.amenities),
    instant_book: bool(one(sp.instant_book)),
    superhost: bool(one(sp.superhost)),
    min_rating: one(sp.min_rating),
    sort_by: one(sp.sort_by),
  }
  const defaults = {
    destination: query.destination,
    check_in: query.check_in,
    check_out: query.check_out,
    adults: Number(query.adults ?? 2),
    children: Number(query.children ?? 0),
    pets: Number(query.pets ?? 0),
  }
  let result: SearchResult
  try {
    result = await stays<SearchResult>("/api/listings", { query })
  } catch (e) {
    if (!(e instanceof StaysError) || e.status !== 400) throw e
    return (
      <div className="flex flex-col gap-6">
        <SearchBar defaults={defaults} compact />
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">{e.message}</p>
      </div>
    )
  }
  const saved = await savedListingIds()
  // Cards link to the listing with the same dates and guests, so its booking panel is filled in.
  const carry = new URLSearchParams(
    (["check_in", "check_out", "adults", "children", "infants", "pets"] as const).flatMap((k) => (query[k] ? [[k, String(query[k])]] : [])),
  )
  const applied = Object.fromEntries(Object.entries(query).filter(([, v]) => v !== undefined && !(Array.isArray(v) && !v.length)))
  const where = query.destination ? query.destination.replace(/^\w/, (c) => c.toUpperCase()) : "Anywhere"

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="search"
        value={{
          filters: applied,
          homes_shown: result.listings.length,
          visible: result.listings.slice(0, 20).map((l) => `${l.id} ${l.title} ₹${l.average_night ?? l.price}/night${l.stay_total ? ` total ₹${l.stay_total}` : ""} ★${l.rating}`),
        }}
      />
      <SearchBar defaults={defaults} compact />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {result.total} home{result.total === 1 ? "" : "s"} · {where}
        </h1>
        <p className="text-sm text-muted-foreground">
          {result.check_in && result.check_out ? dateRange(result.check_in, result.check_out) : "Any dates"} · {guestsLabel(result.guests)}
          {result.unavailable_for_dates > 0 && ` · ${result.unavailable_for_dates} more are booked for these dates`}
        </p>
      </div>
      <Suspense>
        <SearchFilters />
      </Suspense>
      {result.listings.length ? (
        <div className="grid gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" data-testid="search-results">
          {result.listings.map((l) => (
            <ListingCard key={l.id} listing={l} saved={saved.has(l.id)} query={carry.size ? `?${carry}` : ""} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          No homes match. Try other dates, fewer filters, or <Link href="/search" className="text-primary underline">browse everything</Link>.
        </div>
      )}
    </div>
  )
}
