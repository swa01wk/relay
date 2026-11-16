"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { ChevronLeftIcon, ChevronRightIcon, StarIcon, ZapIcon } from "lucide-react"

import { calendarFor, quoteStay } from "@/app/actions"
import { useRelayAction, useScreenState } from "@/components/relay/relay-provider"
import { Button } from "@/components/ui/button"
import { addDays, nightsBetween, rupees, shortDate, todayIst } from "@/lib/format"
import type { CalendarDay, ListingDetail, Quote } from "@/lib/types"
import { cn } from "@/lib/utils"

export type Stay = { check_in: string; check_out: string; adults: number; children: number; infants: number; pets: number }

const DATE = /^\d{4}-\d{2}-\d{2}$/
const field = "h-10 w-full rounded-lg border bg-background px-3 text-sm"

function monthLabel(month: string) {
  return new Date(`${month}-01T12:00:00Z`).toLocaleDateString("en-IN", { month: "long", year: "numeric" })
}
function shiftMonth(month: string, by: number) {
  const d = new Date(`${month}-01T12:00:00Z`)
  d.setUTCMonth(d.getUTCMonth() + by)
  return d.toISOString().slice(0, 7)
}

/** A month grid: click a free night to start, a later night to end. Booked nights are struck out. */
function Calendar({ listingId, stay, onPick }: { listingId: string; stay: Stay; onPick: (day: string) => void }) {
  const [month, setMonth] = React.useState((stay.check_in || todayIst()).slice(0, 7))
  const [days, setDays] = React.useState<CalendarDay[]>([])
  React.useEffect(() => {
    let live = true
    calendarFor(listingId, month).then((r) => live && r.ok && setDays(r.days))
    return () => {
      live = false
    }
  }, [listingId, month])
  const lead = days.length ? (new Date(`${days[0].date}T12:00:00Z`).getUTCDay() + 6) % 7 : 0
  const thisMonth = todayIst().slice(0, 7)
  return (
    <div className="flex flex-col gap-2" aria-label="Availability calendar">
      <div className="flex items-center justify-between">
        <Button type="button" variant="ghost" size="icon" className="size-8" aria-label="Previous month" disabled={month <= thisMonth} onClick={() => setMonth(shiftMonth(month, -1))}>
          <ChevronLeftIcon />
        </Button>
        <span className="text-sm font-medium">{monthLabel(month)}</span>
        <Button type="button" variant="ghost" size="icon" className="size-8" aria-label="Next month" onClick={() => setMonth(shiftMonth(month, 1))}>
          <ChevronRightIcon />
        </Button>
      </div>
      <div className="grid grid-cols-7 gap-0.5 text-center text-[11px]">
        {["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((d) => (
          <span key={d} className="py-1 text-muted-foreground">
            {d}
          </span>
        ))}
        {Array.from({ length: lead }, (_, i) => (
          <span key={`lead-${i}`} />
        ))}
        {days.map((d) => {
          const inRange = stay.check_in && stay.check_out && d.date >= stay.check_in && d.date < stay.check_out
          const edge = d.date === stay.check_in || d.date === stay.check_out
          return (
            <button
              key={d.date}
              type="button"
              disabled={d.past || (!d.available && d.date !== stay.check_out)}
              onClick={() => onPick(d.date)}
              aria-label={`${d.date}${d.available ? `, ₹${d.price}` : ", booked"}`}
              className={cn(
                "flex aspect-square flex-col items-center justify-center rounded-md",
                d.past && "text-muted-foreground/40",
                !d.past && !d.available && "text-muted-foreground/60 line-through",
                !d.past && d.available && "hover:bg-muted",
                inRange && "night-in-range",
                edge && "bg-primary text-primary-foreground hover:bg-primary",
              )}
            >
              <span className="text-xs font-medium">{Number(d.date.slice(8))}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Dates, guests and the price, beside the listing. The guest clicks; the assistant uses SET_STAY.
 * Neither books anything: Reserve goes to the Confirm and pay page.
 */
export function BookingPanel({ listing, initial }: { listing: ListingDetail; initial: Partial<Stay> }) {
  const router = useRouter()
  const [stay, setStay] = React.useState<Stay>({
    check_in: initial.check_in ?? "",
    check_out: initial.check_out ?? "",
    adults: initial.adults ?? 2,
    children: initial.children ?? 0,
    infants: initial.infants ?? 0,
    pets: initial.pets ?? 0,
  })
  const [quote, setQuote] = React.useState<{ quote?: Quote; available?: boolean; error?: string } | null>(null)
  const ready = DATE.test(stay.check_in) && DATE.test(stay.check_out) && stay.check_out > stay.check_in

  React.useEffect(() => {
    if (!ready) return
    let live = true
    quoteStay(listing.id, stay).then((r) => {
      if (!live) return
      setQuote(r.ok ? { quote: r.result.quote, available: r.result.available } : { error: r.error })
    })
    return () => {
      live = false
    }
  }, [listing.id, stay, ready])

  const shownQuote = ready ? quote : null
  const bookUrl = `/book?${new URLSearchParams({ listing: listing.id, ...Object.fromEntries(Object.entries(stay).map(([k, v]) => [k, String(v)])) })}`
  const update = (patch: Partial<Stay>) => setStay((s) => ({ ...s, ...patch }))

  const pick = (day: string) => {
    if (!stay.check_in || stay.check_out || day <= stay.check_in) update({ check_in: day, check_out: "" })
    else update({ check_out: day })
  }

  useScreenState("booking_panel", {
    listing_id: listing.id,
    ...stay,
    nights: ready ? nightsBetween(stay.check_in, stay.check_out) : 0,
    available: shownQuote?.available ?? null,
    total: shownQuote?.quote?.total ?? null,
    problem: shownQuote?.error ?? null,
  })

  useRelayAction(
    "SET_STAY",
    (params) => {
      const next = { ...stay }
      for (const key of ["check_in", "check_out"] as const) {
        if (params[key] === undefined) continue
        const v = String(params[key])
        if (!DATE.test(v)) throw new Error(`${key} must look like 2026-12-20`)
        next[key] = v
      }
      for (const key of ["adults", "children", "infants", "pets"] as const) {
        if (params[key] !== undefined) next[key] = Math.max(key === "adults" ? 1 : 0, Number(params[key]) || 0)
      }
      if (next.check_out <= next.check_in) throw new Error("check_out must be after check_in")
      if (next.adults + next.children > listing.max_guests) throw new Error(`this home sleeps ${listing.max_guests}`)
      if (next.pets && !listing.pets_allowed) throw new Error("pets aren't allowed here")
      setStay(next)
      const url = `/book?${new URLSearchParams({ listing: listing.id, ...Object.fromEntries(Object.entries(next).map(([k, v]) => [k, String(v)])) })}`
      if (params.go_to_checkout) router.push(url)
      return {
        stay: next,
        nights: nightsBetween(next.check_in, next.check_out),
        page: params.go_to_checkout ? "/book (Confirm and pay)" : "listing booking panel",
        next: params.go_to_checkout
          ? "On Confirm and pay, fill the message to the host if needed; only the guest presses the pay button."
          : "The panel shows the price; call again with go_to_checkout: true (or the guest presses Reserve).",
      }
    },
    {
      description:
        "Set dates and guests on the open home's booking panel (omit a field to keep it), showing its price; optionally go on to its Confirm and pay page. Does not book.",
      parameters: {
        type: "object",
        properties: {
          check_in: { type: "string", description: "YYYY-MM-DD" },
          check_out: { type: "string", description: "YYYY-MM-DD" },
          adults: { type: "integer", minimum: 1 },
          children: { type: "integer", minimum: 0 },
          infants: { type: "integer", minimum: 0 },
          pets: { type: "integer", minimum: 0, maximum: 2 },
          go_to_checkout: { type: "boolean", description: "Then open the Confirm and pay page" },
        },
      },
    },
  )

  const q = shownQuote?.quote
  return (
    <aside className="flex flex-col gap-4 rounded-2xl border bg-card p-5 shadow-sm lg:sticky lg:top-24" data-testid="booking-panel" data-relay-ignore>
      <p className="flex items-baseline justify-between">
        <span>
          <span className="text-xl font-semibold">{rupees(q?.average_night ?? listing.price)}</span> <span className="text-sm text-muted-foreground">night</span>
        </span>
        {listing.review_count > 0 && (
          <span className="flex items-center gap-1 text-sm">
            <StarIcon className="size-3.5 fill-current" /> {listing.rating.toFixed(2)} · {listing.review_count} reviews
          </span>
        )}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          Check-in
          <input type="date" className={field} min={todayIst()} value={stay.check_in} onChange={(e) => update({ check_in: e.target.value, check_out: stay.check_out > e.target.value ? stay.check_out : addDays(e.target.value, listing.min_nights) })} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          Check-out
          <input type="date" className={field} min={stay.check_in ? addDays(stay.check_in, 1) : todayIst()} value={stay.check_out} onChange={(e) => update({ check_out: e.target.value })} />
        </label>
        {(
          [
            ["adults", "Adults", 1],
            ["children", "Children", 0],
            ["infants", "Infants", 0],
            ["pets", "Pets", 0],
          ] as const
        ).map(([key, label, min]) => (
          <label key={key} className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
            {label}
            <input
              type="number"
              min={min}
              max={key === "pets" ? (listing.pets_allowed ? 2 : 0) : listing.max_guests}
              className={field}
              value={stay[key]}
              onChange={(e) => update({ [key]: Math.max(min, Number(e.target.value) || 0) })}
            />
          </label>
        ))}
      </div>
      {/* Remounts on the check-in month, so dates set by typing or by the assistant show their month. */}
      <Calendar key={stay.check_in.slice(0, 7) || "now"} listingId={listing.id} stay={stay} onPick={pick} />
      <p className="text-xs text-muted-foreground">
        Minimum stay {listing.min_nights} night{listing.min_nights > 1 ? "s" : ""} · sleeps {listing.max_guests}
        {listing.pets_allowed ? " · pets welcome" : " · no pets"}
      </p>
      {shownQuote?.error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{shownQuote.error}</p>}
      {q && shownQuote?.available === false && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">Some of those nights are already booked.</p>}
      {q && (
        <dl className="flex flex-col gap-1.5 text-sm" data-testid="price-breakdown">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">
              {rupees(q.average_night)} × {q.nights} night{q.nights > 1 ? "s" : ""}
            </dt>
            <dd className="tabular-nums">{rupees(q.accommodation)}</dd>
          </div>
          {q.extra_guest_fee > 0 && (
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Extra guests ({q.extra_guests})</dt>
              <dd className="tabular-nums">{rupees(q.extra_guest_fee)}</dd>
            </div>
          )}
          {q.length_discount > 0 && (
            <div className="flex justify-between text-emerald-700">
              <dt>{q.nights >= 28 ? "Monthly" : "Weekly"} discount ({q.length_discount_pct}%)</dt>
              <dd className="tabular-nums">−{rupees(q.length_discount)}</dd>
            </div>
          )}
          {q.cleaning_fee > 0 && (
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Cleaning fee</dt>
              <dd className="tabular-nums">{rupees(q.cleaning_fee)}</dd>
            </div>
          )}
          {q.pet_fee > 0 && (
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Pet fee</dt>
              <dd className="tabular-nums">{rupees(q.pet_fee)}</dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Service fee</dt>
            <dd className="tabular-nums">{rupees(q.service_fee)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">GST ({q.gst_pct}%)</dt>
            <dd className="tabular-nums">{rupees(q.gst)}</dd>
          </div>
          <div className="mt-1 flex justify-between border-t pt-2 text-base font-semibold">
            <dt>Total</dt>
            <dd className="tabular-nums">{rupees(q.total)}</dd>
          </div>
          {q.nightly.some((n) => n.peak) && <p className="text-xs text-muted-foreground">Includes peak-season nights (20 Dec – 4 Jan).</p>}
        </dl>
      )}
      <Button size="lg" disabled={!q || shownQuote?.available === false} onClick={() => router.push(bookUrl)} data-testid="reserve">
        {listing.instant_book && <ZapIcon />}
        {listing.instant_book ? "Reserve" : "Request to book"}
      </Button>
      <p className="text-center text-xs text-muted-foreground">
        {ready ? `${shortDate(stay.check_in)} – ${shortDate(stay.check_out)} · ` : "Pick dates to see the total · "}You won&apos;t be charged yet
      </p>
    </aside>
  )
}
