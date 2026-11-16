import { Suspense } from "react"
import Link from "next/link"

import { ScreenState } from "@/components/bus/screen-state"
import { SearchFilters, SortTabs } from "@/components/bus/search-filters"
import { SearchForm } from "@/components/bus/search-form"
import { TripCard } from "@/components/bus/trip-card"
import { bus, BusError } from "@/lib/bus"
import { addDays, longDate, rupees, todayIst } from "@/lib/format"
import type { CalendarDay, SearchResult } from "@/lib/types"
import { cn } from "@/lib/utils"

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> }

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)
const bool = (v: string | undefined) => (v === "1" ? true : v === "0" ? false : undefined)

export default async function SearchPage({ searchParams }: Props) {
  const sp = await searchParams
  const from = one(sp.from) ?? "BLR"
  const to = one(sp.to) ?? "HYD"
  const date = one(sp.date) ?? todayIst()
  const filters = {
    ac: bool(one(sp.ac)),
    sleeper: bool(one(sp.sleeper)),
    bus_type: one(sp.bus_type),
    departure_window: one(sp.departure_window),
    operator_id: one(sp.operator_id),
    max_fare: one(sp.max_fare),
    min_rating: one(sp.min_rating),
    amenity: one(sp.amenity),
    sort_by: one(sp.sort_by),
  }
  let result: SearchResult
  try {
    result = await bus<SearchResult>("/api/search", { query: { from_city: from, to_city: to, date, ...filters } })
  } catch (e) {
    if (!(e instanceof BusError) || e.status !== 400) throw e
    return (
      <div className="flex flex-col gap-6">
        <SearchForm from={from} to={to} date={todayIst()} compact />
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">{e.message}</p>
      </div>
    )
  }
  // Fares on the days around the chosen one (the strip under the route).
  const start = date > addDays(todayIst(), 3) ? addDays(date, -3) : todayIst()
  const calendar = result.distance_km
    ? (await bus<{ days: CalendarDay[] }>("/api/fare-calendar", { query: { from_city: from, to_city: to, start_date: start, days: 7 } })).days
    : []
  const applied = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== undefined))
  // The strip links keep the route and filters and change only the date.
  const keep = new URLSearchParams(
    Object.entries(sp).flatMap(([k, v]) => (k !== "date" && typeof one(v) === "string" ? [[k, one(v) as string]] : [])),
  )

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="search"
        value={{
          route: `${result.from_city} → ${result.to_city}`,
          date,
          filters: applied,
          buses_shown: result.trips.length,
          visible: result.trips.slice(0, 20).map((t) => `${t.trip_id} ${t.operator} ${t.departs.slice(11, 16)} ${t.bus_type} ₹${t.fare} ${t.seats_left} left`),
        }}
      />
      <SearchForm from={from} to={to} date={date} compact />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {result.from_city} → {result.to_city}
        </h1>
        <p className="text-sm text-muted-foreground">
          {longDate(date)}
          {result.distance_km ? ` · ${result.distance_km} km` : ""}
        </p>
      </div>
      {calendar.length > 0 && (
        <nav className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" aria-label="Fares by date">
          {calendar.map((d) => {
            const next = new URLSearchParams(keep)
            next.set("date", d.date)
            return (
              <Link
                key={d.date}
                href={`/search?${next}`}
                aria-current={d.date === date ? "date" : undefined}
                className={cn(
                  "flex min-w-24 shrink-0 flex-col rounded-xl border px-3 py-2 text-xs",
                  d.date === date ? "border-primary bg-primary/10 text-primary" : "bg-card hover:border-primary/50",
                )}
              >
                <span className="font-medium">
                  {d.weekday} {Number(d.date.slice(8))}
                </span>
                <span className="text-muted-foreground">{d.cheapest_fare ? `from ${rupees(d.cheapest_fare)}` : "no seats"}</span>
              </Link>
            )
          })}
        </nav>
      )}
      <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
        <Suspense>
          <SearchFilters />
        </Suspense>
        <section className="flex flex-col gap-4" aria-label="Buses" data-testid="search-results">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {result.total} bus{result.total === 1 ? "" : "es"}
              {result.cheapest_fare ? ` · cheapest ${rupees(result.cheapest_fare)}` : ""}
            </p>
            <Suspense>
              <SortTabs />
            </Suspense>
          </div>
          {result.trips.length ? (
            result.trips.map((trip) => <TripCard key={trip.trip_id} trip={trip} />)
          ) : (
            <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
              {result.note ?? "No buses match these filters."}{" "}
              {!result.note && (
                <Link href={`/search?from=${from}&to=${to}&date=${date}`} className="text-primary underline">
                  Clear filters
                </Link>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
