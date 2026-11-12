import Link from "next/link"

import { OperatorLogo, Rating } from "@/components/bus/bits"
import { Button } from "@/components/ui/button"
import { rupees, time } from "@/lib/format"
import { AMENITIES, type TripCard as Trip } from "@/lib/types"

export function TripCard({ trip }: { trip: Trip }) {
  const full = trip.seats_left === 0
  return (
    <article className="flex flex-col gap-4 rounded-2xl border bg-card p-4 sm:p-5" data-testid="trip-card" data-trip-id={trip.trip_id}>
      <div className="flex flex-wrap items-start gap-3">
        <OperatorLogo name={trip.operator} hue={trip.hue} />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold">{trip.operator}</h3>
          <p className="text-xs text-muted-foreground">{trip.bus_type_label}</p>
        </div>
        <Rating value={trip.rating} />
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:grid-cols-[auto_1fr_auto_auto]">
        <div>
          <p className="text-lg font-semibold tabular-nums">{time(trip.departs)}</p>
          <p className="text-xs text-muted-foreground">{trip.boarding_from}</p>
        </div>
        <div className="flex flex-col items-center px-2 text-xs text-muted-foreground sm:px-6">
          <span>{trip.duration}</span>
          <span className="h-px w-full min-w-10 bg-border" />
        </div>
        <div className="text-right sm:text-left">
          <p className="text-lg font-semibold tabular-nums">
            {time(trip.arrives)}
            {trip.arrives_next_day > 0 && <sup className="ml-0.5 text-[10px] font-medium text-muted-foreground">+{trip.arrives_next_day}</sup>}
          </p>
          <p className="text-xs text-muted-foreground">{trip.dropping_at}</p>
        </div>
        <div className="col-span-3 flex items-center justify-between gap-4 border-t pt-3 sm:col-span-1 sm:flex-col sm:items-end sm:border-0 sm:pt-0 sm:pl-6">
          <p className="text-right">
            <span className="block text-xs text-muted-foreground">from</span>
            <span className="text-xl font-semibold tabular-nums">{rupees(trip.fare)}</span>
          </p>
          <Button asChild disabled={full}>
            <Link href={`/trips/${trip.trip_id}`} aria-label={`View seats on ${trip.operator} at ${time(trip.departs)}`}>
              {full ? "Sold out" : "View seats"}
            </Link>
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className={trip.seats_left <= 5 ? "font-medium text-orange-700" : undefined}>
          {trip.seats_left} seat{trip.seats_left === 1 ? "" : "s"} left
        </span>
        {trip.women_only_seats > 0 && <span className="text-pink-700">{trip.women_only_seats} for women only</span>}
        <span aria-hidden="true">·</span>
        {trip.amenities.slice(0, 4).map((a) => (
          <span key={a}>{AMENITIES[a]}</span>
        ))}
        {trip.amenities.length > 4 && <span>+{trip.amenities.length - 4} more</span>}
      </div>
    </article>
  )
}
