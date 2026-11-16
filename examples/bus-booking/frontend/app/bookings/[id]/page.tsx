import Link from "next/link"
import { notFound } from "next/navigation"
import { CheckCircle2Icon, ChevronLeftIcon, MapPinIcon, StarIcon } from "lucide-react"

import { BookingStatus, OperatorLogo } from "@/components/bus/bits"
import { CancelBookingForm, ChangePointsForm, RateTripForm, RescheduleForm } from "@/components/bus/booking-actions"
import { ScreenState } from "@/components/bus/screen-state"
import { bus, BusError } from "@/lib/bus"
import { dateTime, longDate, rupees, shortDate, statusLabel, time } from "@/lib/format"
import type { Booking } from "@/lib/types"

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ booked?: string }> }

export default async function BookingPage({ params, searchParams }: Props) {
  const [{ id }, { booked }] = await Promise.all([params, searchParams])
  let b: Booking
  try {
    b = (await bus<{ booking: Booking }>(`/api/bookings/${id}`)).booking
  } catch (e) {
    if (e instanceof BusError && e.status === 404) notFound()
    throw e
  }

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="booking"
        value={{
          booking_id: b.id,
          pnr: b.pnr,
          status: b.status,
          route: b.route,
          departs: b.departs,
          seats: b.seats,
          can_cancel: b.can_cancel,
          can_reschedule: b.can_reschedule,
          can_change_points: b.can_change_points,
          can_rate: b.can_rate,
        }}
      />
      <Link href="/bookings" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeftIcon className="size-4" /> My trips
      </Link>
      {booked && (
        <div className="flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" role="status">
          <CheckCircle2Icon className="size-5" />
          <span>
            Booked! Your e-ticket is on its way to {b.contact_email}. Show PNR <strong>{b.pnr}</strong> when you board.
          </span>
        </div>
      )}
      <header className="flex flex-wrap items-start gap-4">
        <OperatorLogo name={b.trip.operator} hue={b.trip.hue} className="size-12" />
        <div className="min-w-0 flex-1">
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            {b.route} <BookingStatus status={b.status} />
          </h1>
          <p className="text-sm text-muted-foreground">
            {longDate(b.journey_date)} · {b.trip.operator}, {b.trip.bus_type_label}
          </p>
          <p className="text-xs text-muted-foreground">
            PNR <span className="font-mono font-medium text-foreground">{b.pnr}</span> · booking {b.id} · booked {shortDate(b.booked_at)}
            {b.rescheduled_from ? " · rescheduled" : ""}
          </p>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-6">
          <section className="grid gap-4 rounded-2xl border bg-card p-5 sm:grid-cols-2" aria-label="Journey">
            {[
              ["Boarding", b.boarding_point],
              ["Dropping", b.dropping_point],
            ].map(([label, p]) => {
              const point = p as Booking["boarding_point"]
              return (
                <div key={String(label)} className="flex gap-3">
                  <MapPinIcon className="mt-0.5 size-5 shrink-0 text-primary" />
                  <div>
                    <p className="text-xs text-muted-foreground">{String(label)}</p>
                    <p className="text-lg font-semibold tabular-nums">{time(point.time)}</p>
                    <p className="text-sm">{point.name}</p>
                    <p className="text-xs text-muted-foreground">{point.landmark} · {shortDate(point.time)}</p>
                  </div>
                </div>
              )
            })}
          </section>

          <section className="rounded-2xl border bg-card" aria-label="Passengers">
            <h2 className="border-b px-5 py-3 font-semibold">Passengers</h2>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-5 py-2 font-normal">Seat</th>
                  <th className="py-2 font-normal">Name</th>
                  <th className="py-2 font-normal">Age / gender</th>
                  <th className="px-5 py-2 text-right font-normal">Status</th>
                </tr>
              </thead>
              <tbody>
                {b.passengers.map((p) => (
                  <tr key={`${p.seat}-${p.name}`} className="border-t">
                    <td className="px-5 py-2.5 font-medium">{p.seat}</td>
                    <td className="py-2.5">{p.name}</td>
                    <td className="py-2.5 text-muted-foreground">
                      {p.age} · {p.gender}
                    </td>
                    <td className="px-5 py-2.5 text-right">
                      {p.status === "confirmed" ? (
                        <span className="text-emerald-700">Confirmed</span>
                      ) : (
                        <span className="text-muted-foreground">Cancelled · {rupees(p.refund ?? 0)} refunded</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {b.history.length > 0 && (
            <section className="flex flex-col gap-2 rounded-2xl border bg-card p-5" aria-label="History">
              <h2 className="font-semibold">History</h2>
              <ol className="flex flex-col gap-1.5 text-sm">
                {b.history.map((h) => (
                  <li key={h.at + h.event} className="flex gap-3">
                    <span className="w-36 shrink-0 text-xs text-muted-foreground">{dateTime(h.at)}</span>
                    <span>
                      {statusLabel(h.event)} — {h.detail}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </div>

        <aside className="flex flex-col gap-4">
          <section className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-sm" aria-label="Payment">
            <h2 className="font-semibold">Payment</h2>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Fare</span>
              <span className="tabular-nums">{rupees(b.fare_total)}</span>
            </div>
            {b.discount > 0 && (
              <div className="flex justify-between text-emerald-700">
                <span>Offer {b.coupon}</span>
                <span className="tabular-nums">−{rupees(b.discount)}</span>
              </div>
            )}
            {b.gst > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">GST</span>
                <span className="tabular-nums">{rupees(b.gst)}</span>
              </div>
            )}
            {b.extra_paid > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Reschedule</span>
                <span className="tabular-nums">{rupees(b.extra_paid)}</span>
              </div>
            )}
            {b.refunded > 0 && (
              <div className="flex justify-between text-emerald-700">
                <span>Refunded</span>
                <span className="tabular-nums">−{rupees(b.refunded)}</span>
              </div>
            )}
            <div className="flex justify-between border-t pt-2 font-semibold">
              <span>Paid</span>
              <span className="tabular-nums">{rupees(b.amount_paid)}</span>
            </div>
            <p className="text-xs text-muted-foreground">{b.payment_label}</p>
          </section>
          {b.rating && (
            <p className="flex items-center gap-1 rounded-2xl border bg-card p-4 text-sm">
              You rated this trip {b.rating.stars} <StarIcon className="size-4 fill-amber-400 text-amber-400" />
            </p>
          )}
          {b.can_change_points && <ChangePointsForm booking={b} />}
          {b.can_reschedule && <RescheduleForm booking={b} />}
          {b.can_cancel && <CancelBookingForm key={b.seats.join(",")} booking={b} />}
          {b.can_rate && <RateTripForm booking={b} />}
          {b.status === "upcoming" && !b.can_cancel && (
            <p className="rounded-2xl border border-dashed p-4 text-xs text-muted-foreground">Cancellations close 6 hours before departure.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
