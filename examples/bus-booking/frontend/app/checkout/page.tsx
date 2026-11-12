import Link from "next/link"
import { notFound } from "next/navigation"
import { ChevronLeftIcon, MapPinIcon } from "lucide-react"

import { CheckoutForm } from "@/components/bus/checkout-form"
import { ScreenState } from "@/components/bus/screen-state"
import { bus, BusError } from "@/lib/bus"
import { longDate, time } from "@/lib/format"
import type { MyContext, Quote, TripDetail } from "@/lib/types"

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> }
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)

export default async function CheckoutPage({ searchParams }: Props) {
  const sp = await searchParams
  const tripId = one(sp.trip)
  const seats = (one(sp.seats) ?? "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean)
  if (!tripId) notFound()
  let trip: TripDetail
  try {
    trip = (await bus<{ trip: TripDetail }>(`/api/trips/${tripId}`)).trip
  } catch (e) {
    if (e instanceof BusError && e.status === 404) notFound()
    throw e
  }
  const back = (
    <Link href={`/trips/${trip.trip_id}`} className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ChevronLeftIcon className="size-4" /> Back to the seat map
    </Link>
  )
  let quote: Quote
  try {
    quote = (await bus<{ quote: Quote }>(`/api/trips/${trip.trip_id}/quote`, { query: { seats: seats.join(",") } })).quote
  } catch (e) {
    if (!(e instanceof BusError)) throw e
    return (
      <div className="flex flex-col gap-4">
        {back}
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">{e.message}. Pick seats again.</p>
      </div>
    )
  }
  const me = await bus<MyContext>("/api/me")
  const boarding = trip.boarding_points.find((p) => p.id === one(sp.boarding)) ?? trip.boarding_points[0]
  const dropping = trip.dropping_points.find((p) => p.id === one(sp.dropping)) ?? trip.dropping_points[trip.dropping_points.length - 1]

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="checkout"
        value={{
          trip_id: trip.trip_id,
          seats,
          boarding_point: boarding.id,
          dropping_point: dropping.id,
          total: quote.total,
          saved_travellers: me.saved_travellers.map((t) => `${t.name} (${t.age}, ${t.gender})`),
          note: "Fill the Passenger details page form; only the traveller presses Pay.",
        }}
      />
      {back}
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Passenger details</h1>
        <p className="text-sm text-muted-foreground">
          {trip.from_city} → {trip.to_city} · {trip.operator}, {trip.bus_type_label} · {longDate(trip.date)}
        </p>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="flex items-center gap-1">
            <MapPinIcon className="size-3.5 text-primary" /> Board at {boarding.name}, {time(boarding.time)}
          </span>
          <span className="flex items-center gap-1">
            <MapPinIcon className="size-3.5 text-muted-foreground" /> Drop at {dropping.name}, {time(dropping.time)}
          </span>
        </p>
      </header>
      <CheckoutForm
        tripId={trip.trip_id}
        seats={seats}
        boarding={boarding.id}
        dropping={dropping.id}
        me={me}
        initialQuote={quote}
        seatInfo={trip.seats.filter((s) => seats.includes(s.id))}
      />
    </div>
  )
}
