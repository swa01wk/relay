import Link from "next/link"
import { ArrowRightIcon, BellIcon, BusFrontIcon, MapPinIcon, ShieldCheckIcon, SparklesIcon } from "lucide-react"

import { ScreenState } from "@/components/bus/screen-state"
import { SearchForm } from "@/components/bus/search-form"
import { bus } from "@/lib/bus"
import { addDays, dateTime, rupees, todayIst } from "@/lib/format"
import type { AttentionItem, MyContext, Offer, RouteInfo } from "@/lib/types"

const POPULAR = ["BLR-HYD", "BLR-CHE", "BLR-GOA", "MUM-PUN", "CHE-CBE", "HYD-VJA", "BLR-MYS", "MUM-GOA"]

export default async function HomePage() {
  const [me, { routes }, { offers }, { items }] = await Promise.all([
    bus<MyContext>("/api/me"),
    bus<{ routes: RouteInfo[] }>("/api/routes"),
    bus<{ offers: Offer[] }>("/api/offers"),
    bus<{ items: AttentionItem[] }>("/api/attention"),
  ])
  const popular = POPULAR.map((id) => routes.find((r) => r.route === id)).filter((r): r is RouteInfo => Boolean(r))
  const tomorrow = addDays(todayIst(), 1)

  return (
    <div className="flex flex-col gap-10">
      <ScreenState name="home" value={{ next_trip: me.next_trip?.id ?? null, attention: items.length, popular_routes: popular.map((r) => r.route) }} />
      <section className="flex flex-col gap-5 rounded-3xl bg-gradient-to-br from-primary to-[oklch(0.38_0.13_275)] px-6 py-10 text-primary-foreground sm:px-10">
        <div className="max-w-2xl">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Bus tickets across the South and West, by asking.</h1>
          <p className="mt-2 text-primary-foreground/80">
            Twelve cities, eight operators, sleepers and seaters. Say “AC sleeper to Hyderabad tomorrow night, two lower berths” and the
            assistant finds the bus, picks the seats and fills the passenger details for you.
          </p>
        </div>
        <div className="text-foreground">
          <SearchForm date={tomorrow} />
        </div>
      </section>

      {(me.next_trip || items.length > 0) && (
        <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          {me.next_trip && (
            <Link href={`/bookings/${me.next_trip.id}`} className="group flex flex-col gap-2 rounded-2xl border bg-card p-5 hover:border-primary">
              <span className="flex items-center gap-2 text-xs font-medium text-primary">
                <BusFrontIcon className="size-4" /> Your next trip
              </span>
              <span className="text-lg font-semibold">{me.next_trip.route}</span>
              <span className="text-sm text-muted-foreground">
                {dateTime(me.next_trip.departs)} · {me.next_trip.operator} · seats {me.next_trip.seats.join(", ")}
              </span>
              <span className="flex items-center gap-1 text-sm">
                <MapPinIcon className="size-3.5" /> Board at {me.next_trip.boarding_point}
              </span>
              <span className="mt-1 flex items-center gap-1 text-sm font-medium text-primary">
                View ticket <ArrowRightIcon className="size-4 transition group-hover:translate-x-0.5" />
              </span>
            </Link>
          )}
          {items.length > 0 && (
            <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
              <span className="flex items-center gap-2 text-xs font-medium text-amber-700">
                <BellIcon className="size-4" /> Needs your attention
              </span>
              <ul className="flex flex-col gap-2 text-sm">
                {items.slice(0, 4).map((item) => (
                  <li key={`${item.kind}-${item.booking_id}`}>
                    <Link href={`/bookings/${item.booking_id}`} className="hover:underline">
                      {item.text}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold tracking-tight">Popular routes</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {popular.map((r) => (
            <Link
              key={r.route}
              href={`/search?from=${r.from}&to=${r.to}&date=${tomorrow}`}
              className="flex flex-col gap-1 rounded-xl border bg-card p-4 hover:border-primary"
            >
              <span className="font-medium">
                {r.from_city} → {r.to_city}
              </span>
              <span className="text-xs text-muted-foreground">
                {r.distance_km} km · {r.typical_duration} · {r.buses_per_day} buses a day
              </span>
              {r.fares_from && <span className="text-sm">from <span className="font-semibold">{rupees(r.fares_from)}</span></span>}
            </Link>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex items-end justify-between">
          <h2 className="text-xl font-semibold tracking-tight">Offers</h2>
          <Link href="/offers" className="text-sm text-primary hover:underline">
            All offers
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {offers.map((o) => (
            <div key={o.code} className="flex flex-col gap-1 rounded-xl border border-dashed border-primary/40 bg-accent/40 p-4">
              <span className="font-mono text-sm font-semibold tracking-wide text-primary">{o.code}</span>
              <span className="text-sm font-medium">{o.title}</span>
              <span className="text-xs text-muted-foreground">{o.description}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 text-sm sm:grid-cols-3">
        {[
          [SparklesIcon, "Ask, don't scroll", "Search, pick seats, fill passenger details and change trips by voice or text."],
          [ShieldCheckIcon, "You approve every booking", "The assistant prepares bookings and changes; nothing is paid or cancelled until you approve."],
          [MapPinIcon, "Board where it suits you", "Four boarding points per city; change yours until 4 hours before departure."],
        ].map(([Icon, title, text]) => {
          const I = Icon as typeof SparklesIcon
          return (
            <div key={String(title)} className="flex gap-3 rounded-xl border bg-card p-4">
              <I className="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <p className="font-medium">{String(title)}</p>
                <p className="text-muted-foreground">{String(text)}</p>
              </div>
            </div>
          )
        })}
      </section>
    </div>
  )
}
