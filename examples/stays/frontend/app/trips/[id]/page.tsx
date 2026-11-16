import Link from "next/link"
import { notFound } from "next/navigation"
import { CheckCircle2Icon, ChevronLeftIcon, ClockIcon, KeyRoundIcon, ParkingSquareIcon, WifiIcon } from "lucide-react"

import { ListingArt } from "@/components/stays/listing-art"
import { ScreenState } from "@/components/stays/screen-state"
import { CancelTripForm, ChangeTripForm, MessageThread, ReviewForm } from "@/components/stays/trip-actions"
import { TripStatusBadge } from "@/components/stays/trip-status"
import { stays, StaysError } from "@/lib/stays"
import { dateTime, dayDate, guestsLabel, rupees, statusLabel } from "@/lib/format"
import { POLICY_LABEL, type Trip } from "@/lib/types"

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ booked?: string }> }

export default async function TripPage({ params, searchParams }: Props) {
  const [{ id }, { booked }] = await Promise.all([params, searchParams])
  let t: Trip
  try {
    t = (await stays<{ trip: Trip }>(`/api/trips/${id}`)).trip
  } catch (e) {
    if (e instanceof StaysError && e.status === 404) notFound()
    throw e
  }
  const p = t.price

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="trip"
        value={{ trip_id: t.id, code: t.code, status: t.status, home: t.listing.title, check_in: t.check_in, check_out: t.check_out, refund_pct_now: t.refund_pct_now, can_change: t.can_change, can_review: t.can_review }}
      />
      <Link href="/trips" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeftIcon className="size-4" /> Trips
      </Link>
      {booked && (
        <div className="flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" role="status">
          <CheckCircle2Icon className="size-5" />
          {t.status === "requested"
            ? `Request sent. ${t.host.name} usually replies ${t.host.response_time}; you're only charged if they accept.`
            : `You're going to ${t.listing.destination_name}! Confirmation code ${t.code}.`}
        </div>
      )}
      <header className="flex flex-wrap items-start gap-4">
        <ListingArt hue={t.listing.hue} icon={t.listing.icon} className="size-20 shrink-0 rounded-xl" />
        <div className="min-w-0 flex-1">
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            {t.listing.title} <TripStatusBadge status={t.status} />
          </h1>
          <p className="text-sm text-muted-foreground">
            {t.listing.area}, {t.listing.destination_name} · hosted by {t.host.name}
            {t.host.superhost ? " (Superhost)" : ""}
          </p>
          <p className="text-xs text-muted-foreground">
            Code <span className="font-mono font-medium text-foreground">{t.code}</span> · {t.id} · booked {dateTime(t.booked_at)} ·{" "}
            <Link href={`/listings/${t.listing_id}`} className="underline">
              view home
            </Link>
          </p>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-6">
          <section className="grid gap-4 rounded-2xl border bg-card p-5 sm:grid-cols-3" aria-label="Stay">
            <div>
              <p className="text-xs text-muted-foreground">Check-in</p>
              <p className="font-semibold">{dayDate(t.check_in)}</p>
              <p className="text-sm text-muted-foreground">from {t.check_in_from}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Check-out</p>
              <p className="font-semibold">{dayDate(t.check_out)}</p>
              <p className="text-sm text-muted-foreground">by {t.check_out_by}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Guests</p>
              <p className="font-semibold">{guestsLabel(t)}</p>
              <p className="text-sm text-muted-foreground">{t.nights} nights</p>
            </div>
          </section>

          {t.house_manual && (
            <section className="flex flex-col gap-3 rounded-2xl border bg-card p-5 text-sm" aria-label="Check-in details">
              <h2 className="font-semibold">Getting in</h2>
              <p className="flex gap-3">
                <KeyRoundIcon className="size-4 shrink-0" /> {t.house_manual.check_in}
              </p>
              <p className="flex gap-3">
                <WifiIcon className="size-4 shrink-0" /> {t.house_manual.wifi}
              </p>
              <p className="flex gap-3">
                <ParkingSquareIcon className="size-4 shrink-0" /> {t.house_manual.parking}
              </p>
            </section>
          )}

          <MessageThread trip={t} />

          <section className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-sm" aria-label="History">
            <h2 className="font-semibold">History</h2>
            <ol className="flex flex-col gap-1.5">
              {t.history.map((h) => (
                <li key={h.at + h.event} className="flex gap-3">
                  <ClockIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  <span className="w-32 shrink-0 text-xs text-muted-foreground">{dateTime(h.at)}</span>
                  <span>
                    {statusLabel(h.event)} — {h.detail}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="flex flex-col gap-4">
          <section className="flex flex-col gap-1.5 rounded-2xl border bg-card p-5 text-sm" aria-label="Payment">
            <h2 className="mb-1 font-semibold">Payment</h2>
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                {rupees(p.average_night)} × {p.nights} nights
              </span>
              <span className="tabular-nums">{rupees(p.accommodation)}</span>
            </div>
            {p.length_discount > 0 && (
              <div className="flex justify-between text-emerald-700">
                <span>Length-of-stay discount</span>
                <span className="tabular-nums">−{rupees(p.length_discount)}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Fees and GST</span>
              <span className="tabular-nums">{rupees(p.total - p.accommodation - p.extra_guest_fee + p.length_discount)}</span>
            </div>
            {t.extra_paid > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Paid for changes</span>
                <span className="tabular-nums">{rupees(t.extra_paid)}</span>
              </div>
            )}
            {t.refund > 0 && (
              <div className="flex justify-between text-emerald-700">
                <span>Refunded</span>
                <span className="tabular-nums">−{rupees(t.refund)}</span>
              </div>
            )}
            <div className="flex justify-between border-t pt-2 font-semibold">
              <span>{t.status === "requested" ? "To pay if accepted" : "Paid"}</span>
              <span className="tabular-nums">{rupees(t.status === "requested" ? t.total : t.amount_paid)}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              {t.payment_label} · {POLICY_LABEL[t.cancellation_policy]} cancellation: {t.cancellation_policy_text}
            </p>
          </section>
          {t.can_change && <ChangeTripForm key={`${t.check_in}-${t.check_out}-${t.guests}`} trip={t} />}
          {t.can_cancel && <CancelTripForm trip={t} />}
          {t.can_review && <ReviewForm trip={t} />}
          {t.reviewed && <p className="rounded-2xl border bg-card p-4 text-sm">You reviewed this stay — thank you.</p>}
        </aside>
      </div>
    </div>
  )
}
