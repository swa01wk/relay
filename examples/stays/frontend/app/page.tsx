import Link from "next/link"
import { ArrowRightIcon, BellIcon, LuggageIcon } from "lucide-react"

import { ListingArt } from "@/components/stays/listing-art"
import { ListingCard } from "@/components/stays/listing-card"
import { ScreenState } from "@/components/stays/screen-state"
import { SearchBar } from "@/components/stays/search-bar"
import { savedListingIds, stays } from "@/lib/stays"
import { dateRange, rupees } from "@/lib/format"
import { KINDS, type AttentionItem, type Destination, type MyContext, type SearchResult } from "@/lib/types"

const KIND_HUE: Record<string, number> = { beach: 200, mountains: 150, countryside: 110, lakes: 230, city: 30 }

export default async function HomePage() {
  const [me, { destinations }, top, { items }, saved] = await Promise.all([
    stays<MyContext>("/api/me"),
    stays<{ destinations: Destination[] }>("/api/destinations"),
    stays<SearchResult>("/api/listings", { query: { sort_by: "rating" } }),
    stays<{ items: AttentionItem[] }>("/api/attention"),
    savedListingIds(),
  ])

  return (
    <div className="flex flex-col gap-10">
      <ScreenState name="home" value={{ next_trip: me.next_trip?.id ?? null, attention: items.length }} />
      <section className="flex flex-col gap-5">
        <div className="max-w-2xl">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Find a home for your next trip — just ask.</h1>
          <p className="mt-2 text-muted-foreground">
            Villas, houseboats, havelis and hill cottages in twelve places across India. Say “a pool villa in Goa for six over New Year” and the
            assistant finds it, checks the dates and fills in the booking for you.
          </p>
        </div>
        <SearchBar />
        <nav className="flex flex-wrap gap-2" aria-label="Kinds of places">
          {Object.entries(KINDS).map(([k, label]) => (
            <Link key={k} href={`/search?destination=${k}`} className="rounded-full border px-4 py-1.5 text-sm hover:border-foreground">
              {label}
            </Link>
          ))}
        </nav>
      </section>

      {(me.next_trip || items.length > 0) && (
        <section className="grid gap-4 lg:grid-cols-2">
          {me.next_trip && (
            <Link href={`/trips/${me.next_trip.id}`} className="group flex gap-4 rounded-2xl border bg-card p-4 hover:border-primary">
              <ListingArt hue={me.next_trip.hue} icon={me.next_trip.icon} className="size-24 shrink-0 rounded-xl" />
              <div className="flex flex-col gap-1">
                <span className="flex items-center gap-1.5 text-xs font-medium text-primary">
                  <LuggageIcon className="size-4" /> Your next trip
                </span>
                <span className="font-semibold">{me.next_trip.title}</span>
                <span className="text-sm text-muted-foreground">
                  {me.next_trip.area}, {me.next_trip.destination} · {dateRange(me.next_trip.check_in, me.next_trip.check_out)}
                </span>
                <span className="flex items-center gap-1 text-sm font-medium text-primary">
                  View trip <ArrowRightIcon className="size-4 transition group-hover:translate-x-0.5" />
                </span>
              </div>
            </Link>
          )}
          {items.length > 0 && (
            <div className="flex flex-col gap-3 rounded-2xl border bg-card p-4">
              <span className="flex items-center gap-1.5 text-xs font-medium text-amber-700">
                <BellIcon className="size-4" /> For you
              </span>
              <ul className="flex flex-col gap-2 text-sm">
                {items.slice(0, 4).map((item) => (
                  <li key={`${item.kind}-${item.trip_id}`}>
                    <Link href={`/trips/${item.trip_id}`} className="hover:underline">
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
        <h2 className="text-xl font-semibold tracking-tight">Where to next</h2>
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {destinations.map((d) => (
            <Link key={d.key} href={`/search?destination=${encodeURIComponent(d.name)}`} className="group flex flex-col gap-2">
              <ListingArt hue={KIND_HUE[d.kind]} icon={d.kind === "city" ? "building" : d.kind === "lakes" ? "sailboat" : d.kind === "beach" ? "home" : "tree"} className="aspect-square rounded-2xl transition group-hover:scale-[1.02]" />
              <span className="text-sm font-medium">{d.name}</span>
              <span className="-mt-2 text-xs text-muted-foreground">
                {d.listings} homes · from {rupees(d.price_from)}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex items-end justify-between">
          <h2 className="text-xl font-semibold tracking-tight">Guest favourites</h2>
          <Link href="/search?sort_by=rating" className="text-sm text-primary hover:underline">
            Show all
          </Link>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {top.listings.slice(0, 8).map((l) => (
            <ListingCard key={l.id} listing={l} saved={saved.has(l.id)} />
          ))}
        </div>
      </section>
    </div>
  )
}
