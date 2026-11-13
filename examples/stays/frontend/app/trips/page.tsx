import Link from "next/link"

import { ListingArt } from "@/components/stays/listing-art"
import { ScreenState } from "@/components/stays/screen-state"
import { TripStatusBadge } from "@/components/stays/trip-status"
import { stays } from "@/lib/stays"
import { dateRange, rupees, statusLabel } from "@/lib/format"
import { TRIP_STATUSES, type TripBrief } from "@/lib/types"
import { cn } from "@/lib/utils"

type Props = { searchParams: Promise<{ status?: string }> }

export default async function TripsPage({ searchParams }: Props) {
  const { status } = await searchParams
  const valid = TRIP_STATUSES.find((s) => s === status)
  const { trips, total } = await stays<{ trips: TripBrief[]; total: number }>("/api/trips", { query: { status: valid } })

  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="trips" value={{ status: valid ?? "all", shown: trips.length, visible: trips.map((t) => `${t.id} ${t.code} ${t.title} ${t.check_in} ${t.status}`) }} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Trips</h1>
        <p className="text-sm text-muted-foreground">
          {total} trip{total === 1 ? "" : "s"}
        </p>
      </div>
      <nav className="flex flex-wrap gap-1.5" aria-label="Filter by status">
        {[undefined, ...TRIP_STATUSES].map((s) => (
          <Link
            key={s ?? "all"}
            href={s ? `/trips?status=${s}` : "/trips"}
            aria-current={valid === s ? "page" : undefined}
            className={cn("rounded-full border px-3 py-1 text-sm", valid === s ? "border-foreground bg-foreground text-background" : "hover:border-foreground/60")}
          >
            {s ? (s === "in_stay" ? "Staying now" : statusLabel(s)) : "All"}
          </Link>
        ))}
      </nav>
      {trips.length ? (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="trip-list">
          {trips.map((t) => (
            <li key={t.id}>
              <Link href={`/trips/${t.id}`} className="group flex flex-col gap-2 rounded-2xl border bg-card p-3 hover:border-primary">
                <ListingArt hue={t.hue} icon={t.icon} className="aspect-[16/9] rounded-xl" />
                <div className="flex items-start justify-between gap-2 px-1">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{t.title}</p>
                    <p className="text-sm text-muted-foreground">
                      {t.area}, {t.destination} · {dateRange(t.check_in, t.check_out)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {t.guests} guests · hosted by {t.host} · {rupees(t.amount_paid)}
                    </p>
                  </div>
                  <TripStatusBadge status={t.status} />
                </div>
                {t.can_review && <p className="px-1 text-xs font-medium text-amber-700">Write a review</p>}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          No trips here yet. <Link href="/search" className="text-primary underline">Find a place to stay</Link>
        </div>
      )}
    </div>
  )
}
