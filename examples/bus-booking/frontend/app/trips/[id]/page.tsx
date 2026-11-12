import Link from "next/link"
import { notFound } from "next/navigation"
import { ChevronLeftIcon } from "lucide-react"

import { OperatorLogo, Rating } from "@/components/bus/bits"
import { ScreenState } from "@/components/bus/screen-state"
import { SeatPicker } from "@/components/bus/seat-picker"
import { bus, BusError } from "@/lib/bus"
import { longDate, time } from "@/lib/format"
import type { TripDetail } from "@/lib/types"

export default async function TripPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  let trip: TripDetail
  try {
    trip = (await bus<{ trip: TripDetail }>(`/api/trips/${id}`)).trip
  } catch (e) {
    if (e instanceof BusError && e.status === 404) notFound()
    throw e
  }

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="trip"
        value={{
          trip_id: trip.trip_id,
          bus: `${trip.operator} ${trip.bus_type_label}`,
          departs: trip.departs,
          seats_available: trip.seats_left,
          women_only_seats: trip.seats.filter((s) => s.women_only).map((s) => s.id),
          bookable: trip.bookable,
        }}
      />
      <Link href={`/search?from=${trip.from}&to=${trip.to}&date=${trip.date}`} className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeftIcon className="size-4" /> All buses {trip.from_city} → {trip.to_city}
      </Link>
      <header className="flex flex-wrap items-start gap-4">
        <OperatorLogo name={trip.operator} hue={trip.hue} className="size-12" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">{trip.operator}</h1>
          <p className="text-sm text-muted-foreground">
            {trip.bus_type_label} · {longDate(trip.date)} · {time(trip.departs)} → {time(trip.arrives)}
            {trip.arrives_next_day > 0 ? " (next day)" : ""} · {trip.duration}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{trip.amenity_labels.join(" · ")}</p>
        </div>
        <Rating value={trip.rating} />
      </header>
      {trip.bookable ? (
        <SeatPicker trip={trip} />
      ) : (
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">Booking for this bus has closed.</p>
      )}
      <section className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Cancellation policy</h2>
          <table className="text-sm">
            <tbody>
              {trip.cancellation_policy.map((line) => (
                <tr key={line.window} className="border-t first:border-0">
                  <td className="py-1.5 pr-4 text-muted-foreground">{line.window}</td>
                  <td className="py-1.5 text-right font-medium">{line.charge_pct === null ? "Not cancellable" : `${line.charge_pct}% charge`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">What travellers say</h2>
          {trip.latest_reviews.map((r) => (
            <div key={r.id} className="text-sm">
              <p className="flex items-center gap-2">
                <Rating value={r.rating} /> <span className="font-medium">{r.author}</span>
                <span className="text-xs text-muted-foreground">{r.date}</span>
              </p>
              <p className="mt-1 text-muted-foreground">{r.comment}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
