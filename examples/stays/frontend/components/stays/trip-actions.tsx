"use client"

import * as React from "react"
import { SendIcon, StarIcon } from "lucide-react"
import { toast } from "sonner"

import { cancelTrip, changeTrip, messageHost, writeReview, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { addDays, dateTime, rupees, todayIst } from "@/lib/format"
import { CANCEL_REASONS, SUB_RATINGS, type Trip } from "@/lib/types"
import { cn } from "@/lib/utils"

const input = "h-9 w-full rounded-md border bg-background px-3 text-sm"
const card = "flex flex-col gap-3 rounded-2xl border bg-card p-5"

function useResult(state: ActionResult | null, success: string, onOk?: () => void) {
  React.useEffect(() => {
    if (state?.ok) {
      toast.success(state.message ?? success)
      onOk?.()
    } else if (state?.error) toast.error(state.error)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])
}

export function CancelTripForm({ trip }: { trip: Trip }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(cancelTrip.bind(null, trip.id), null)
  useResult(state, "Trip cancelled")
  const paid = trip.amount_paid
  const pct = trip.refund_pct_now ?? 0
  const refund = trip.status === "requested" ? 0 : pct === 100 ? paid : Math.round(((paid - trip.price.service_fee) * pct) / 100)
  return (
    <form action={action} className={card} data-relay-form="Cancel trip" aria-label="Cancel trip">
      <h3 className="font-medium">{trip.status === "requested" ? "Withdraw request" : "Cancel trip"}</h3>
      <p className="text-sm">
        {trip.status === "requested" ? (
          "Nothing has been charged."
        ) : (
          <>
            Refund now: <span className="font-medium">{rupees(refund)}</span> ({pct}%) to {trip.payment_label}.
          </>
        )}
      </p>
      {trip.full_refund_until && pct === 100 && <p className="text-xs text-muted-foreground">Full refund until {dateTime(trip.full_refund_until)}.</p>}
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
      <Button type="submit" variant="destructive" disabled={pending} className="self-start">
        {trip.status === "requested" ? "Withdraw request" : "Cancel trip"}
      </Button>
    </form>
  )
}

export function ChangeTripForm({ trip }: { trip: Trip }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(changeTrip.bind(null, trip.id), null)
  useResult(state, "Trip updated")
  const today = todayIst()
  return (
    <form action={action} className={card} data-relay-form="Change trip" aria-label="Change trip">
      <h3 className="font-medium">Change dates or guests</h3>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-sm">
          Check-in
          <input type="date" name="check_in" min={today} defaultValue={trip.check_in} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Check-out
          <input type="date" name="check_out" min={addDays(today, 1)} defaultValue={trip.check_out} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Adults
          <input type="number" name="adults" min={1} max={trip.listing.max_guests} defaultValue={trip.adults} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Children
          <input type="number" name="children" min={0} max={trip.listing.max_guests} defaultValue={trip.children} className={input} />
        </label>
      </div>
      <p className="text-xs text-muted-foreground">You pay any increase; a lower price is refunded while the trip is fully refundable.</p>
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        Save changes
      </Button>
    </form>
  )
}

export function MessageThread({ trip }: { trip: Trip }) {
  const formRef = React.useRef<HTMLFormElement>(null)
  const endRef = React.useRef<HTMLDivElement>(null)
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(messageHost.bind(null, trip.id), null)
  useResult(state, "Message sent", () => formRef.current?.reset())
  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" })
  }, [trip.messages.length])
  return (
    <section className="flex flex-col gap-3 rounded-2xl border bg-card p-5" aria-label="Messages">
      <h2 className="font-semibold">Messages with {trip.host.name}</h2>
      <div className="flex max-h-80 flex-col gap-2 overflow-y-auto">
        {trip.messages.length === 0 && <p className="text-sm text-muted-foreground">No messages yet.</p>}
        {trip.messages.map((m, i) => (
          <div key={i} className={cn("max-w-[80%] rounded-xl px-3 py-2 text-sm", m.from === "guest" ? "self-end bg-primary text-primary-foreground" : "self-start bg-muted")}>
            <p>{m.text}</p>
            <p className={cn("mt-0.5 text-[10px]", m.from === "guest" ? "text-primary-foreground/70" : "text-muted-foreground")}>
              {m.name} · {dateTime(m.at)}
            </p>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {trip.can_message && (
        <form ref={formRef} action={action} className="flex gap-2" data-relay-form="Message host" aria-label="Message host">
          <input name="message" required maxLength={1000} placeholder={`Message ${trip.host.name}…`} className={input} />
          <Button type="submit" size="icon" disabled={pending} aria-label="Send">
            <SendIcon />
          </Button>
        </form>
      )}
    </section>
  )
}

export function ReviewForm({ trip }: { trip: Trip }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(writeReview.bind(null, trip.id), null)
  const [stars, setStars] = React.useState(0)
  useResult(state, "Thanks for your review")
  return (
    <form action={action} className={card} data-relay-form="Write a review" aria-label="Write a review">
      <h3 className="font-medium">How was your stay?</h3>
      <fieldset className="flex gap-1">
        <legend className="sr-only">Overall rating</legend>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n} className="cursor-pointer" aria-label={`${n} star${n === 1 ? "" : "s"}`}>
            <input type="radio" name="rating" value={n} required className="sr-only" checked={stars === n} onChange={() => setStars(n)} />
            <StarIcon className={`size-6 ${n <= stars ? "fill-amber-400 text-amber-400" : "text-muted-foreground"}`} />
          </label>
        ))}
      </fieldset>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(SUB_RATINGS).map(([k, label]) => (
          <label key={k} className="flex items-center justify-between gap-2 text-xs">
            {label}
            <select name={k} defaultValue="" className="h-8 rounded-md border bg-background px-2">
              <option value="">–</option>
              {[5, 4, 3, 2, 1].map((n) => (
                <option key={n} value={n}>
                  {n}★
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Your review
        <textarea name="comment" required minLength={20} maxLength={2000} rows={4} className="rounded-md border bg-background px-3 py-2" placeholder="What did you love? Anything future guests should know?" />
      </label>
      {trip.review_until && <p className="text-xs text-muted-foreground">You can review until {dateTime(trip.review_until)}.</p>}
      <Button type="submit" disabled={pending || !stars} className="self-start">
        Publish review
      </Button>
    </form>
  )
}
