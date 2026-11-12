"use client"

import * as React from "react"
import { StarIcon } from "lucide-react"
import { toast } from "sonner"

import { cancelBooking, changePoints, rateTrip, rescheduleBooking, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { addDays, rupees, time, todayIst } from "@/lib/format"
import { CANCEL_REASONS, type Booking } from "@/lib/types"

const input = "h-9 w-full rounded-md border bg-background px-3 text-sm"
const card = "flex flex-col gap-3 rounded-2xl border bg-card p-5"

function useResult(state: ActionResult | null, success: string) {
  React.useEffect(() => {
    if (state?.ok) toast.success(state.message ?? success)
    else if (state?.error) toast.error(state.error)
  }, [state, success])
}

/** Cancel all or some seats. A page form: the assistant can tick seats and pick a reason; the traveller confirms. */
export function CancelBookingForm({ booking }: { booking: Booking }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(cancelBooking.bind(null, booking.id), null)
  const active = booking.passengers.filter((p) => p.status === "confirmed")
  const [chosen, setChosen] = React.useState<string[]>(active.map((p) => p.seat))
  useResult(state, "Cancelled — your refund is on its way")
  const pct = booking.cancellation_charge_pct ?? 0
  const paid = active.filter((p) => chosen.includes(p.seat)).reduce((sum, p) => sum + p.paid, 0)
  const charge = active.filter((p) => chosen.includes(p.seat)).reduce((sum, p) => sum + Math.round((p.paid * pct) / 100), 0)
  return (
    <form action={action} className={card} data-relay-form="Cancel booking" aria-label="Cancel booking">
      <h3 className="font-medium">Cancel seats</h3>
      <fieldset className="flex flex-col gap-1.5 text-sm">
        <legend className="mb-1 text-muted-foreground">Seats to cancel</legend>
        {active.map((p) => (
          <label key={p.seat} className="flex items-center gap-2">
            <input
              type="checkbox"
              name="seats"
              value={p.seat}
              checked={chosen.includes(p.seat)}
              onChange={(e) => setChosen((c) => (e.target.checked ? [...c, p.seat] : c.filter((s) => s !== p.seat)))}
              className="accent-[var(--primary)]"
            />
            {p.seat} — {p.name}
          </label>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1 text-sm">
        Reason
        <select name="reason" className={input} defaultValue="change_of_plans">
          {Object.entries(CANCEL_REASONS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <p className="text-sm">
        Charge {pct}%: {rupees(charge)} · <span className="font-medium">refund {rupees(paid - charge)}</span> to {booking.payment_label}
      </p>
      {booking.charges_rise_at && (
        <p className="text-xs text-amber-700">
          From {new Date(booking.charges_rise_at.from).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" })} the charge is{" "}
          {booking.charges_rise_at.charge_pct === null ? "no longer refundable" : `${booking.charges_rise_at.charge_pct}%`}.
        </p>
      )}
      <Button type="submit" variant="destructive" disabled={pending || !chosen.length} className="self-start">
        Cancel {chosen.length === active.length ? "booking" : `${chosen.length} seat${chosen.length === 1 ? "" : "s"}`}
      </Button>
    </form>
  )
}

export function ChangePointsForm({ booking }: { booking: Booking }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(changePoints.bind(null, booking.id), null)
  useResult(state, "Boarding details updated")
  return (
    <form action={action} className={card} data-relay-form="Change boarding point" aria-label="Change boarding point">
      <h3 className="font-medium">Change boarding or dropping point</h3>
      <label className="flex flex-col gap-1 text-sm">
        Boarding point
        <select name="boarding_point" className={input} defaultValue={booking.boarding_point.id}>
          {booking.boarding_points.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.landmark}) — {time(p.time)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Dropping point
        <select name="dropping_point" className={input} defaultValue={booking.dropping_point.id}>
          {booking.dropping_points.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.landmark}) — {time(p.time)}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        Save points
      </Button>
    </form>
  )
}

export function RescheduleForm({ booking }: { booking: Booking }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(rescheduleBooking.bind(null, booking.id), null)
  useResult(state, "Trip moved")
  const today = todayIst()
  return (
    <form action={action} className={card} data-relay-form="Reschedule trip" aria-label="Reschedule trip">
      <h3 className="font-medium">Reschedule</h3>
      <p className="text-xs text-muted-foreground">Same bus, another date. ₹100 fee plus any fare difference; once per booking.</p>
      <label className="flex flex-col gap-1 text-sm">
        New date
        <input type="date" name="new_date" required min={today} max={addDays(today, 60)} className={input} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Seats on the new date (optional)
        <input name="seats" placeholder={booking.seats.join(", ")} className={input} />
      </label>
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        Reschedule
      </Button>
    </form>
  )
}

export function RateTripForm({ booking }: { booking: Booking }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(rateTrip.bind(null, booking.id), null)
  const [stars, setStars] = React.useState(0)
  useResult(state, "Thanks for rating your trip")
  return (
    <form action={action} className={card} data-relay-form="Rate trip" aria-label="Rate trip">
      <h3 className="font-medium">How was {booking.trip.operator}?</h3>
      <fieldset className="flex gap-1">
        <legend className="sr-only">Rating</legend>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n} className="cursor-pointer" aria-label={`${n} star${n === 1 ? "" : "s"}`}>
            <input type="radio" name="rating" value={n} required className="sr-only" checked={stars === n} onChange={() => setStars(n)} />
            <StarIcon className={`size-6 ${n <= stars ? "fill-amber-400 text-amber-400" : "text-muted-foreground"}`} />
          </label>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1 text-sm">
        Review (optional)
        <textarea name="comment" maxLength={1000} rows={3} className="rounded-md border bg-background px-3 py-2" placeholder="Punctuality, comfort, staff…" />
      </label>
      <Button type="submit" disabled={pending || !stars} className="self-start">
        Submit rating
      </Button>
    </form>
  )
}
