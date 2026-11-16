"use client"

import * as React from "react"
import { Loader2Icon, LockIcon, UserPlusIcon } from "lucide-react"

import { bookTickets, quoteFor, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { rupees } from "@/lib/format"
import { GENDERS, PAYMENT_METHODS, type MyContext, type Quote, type Seat, type Traveller } from "@/lib/types"

const input = "h-10 w-full rounded-md border bg-background px-3 text-sm aria-invalid:border-destructive"

/**
 * Passenger details and payment. Native inputs named like the book_tickets tool's fields on
 * purpose: the assistant fills this page form from the chat ("me and Rahul") — and only the
 * traveller presses Pay.
 */
export function CheckoutForm({
  tripId,
  seats,
  boarding,
  dropping,
  me,
  initialQuote,
  seatInfo,
}: {
  tripId: string
  seats: string[]
  boarding: string
  dropping: string
  me: MyContext
  initialQuote: Quote
  seatInfo: Seat[]
}) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(bookTickets, null)
  const [quote, setQuote] = React.useState(initialQuote)
  const [couponNote, setCouponNote] = React.useState<string | null>(null)
  const [checking, startCheck] = React.useTransition()
  const formRef = React.useRef<HTMLFormElement>(null)
  const err = (name: string) => state?.fields?.[name]
  const self: Traveller = { id: "me", name: me.traveller.name, age: me.traveller.age, gender: me.traveller.gender as Traveller["gender"] }
  const people = [self, ...me.saved_travellers]

  const fillPassenger = (n: number, t: Traveller) => {
    const form = formRef.current
    if (!form) return
    const set = (name: string, value: string) => {
      const el = form.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement | null
      if (el) el.value = value
    }
    set(`passenger_${n}_name`, t.name)
    set(`passenger_${n}_age`, String(t.age))
    set(`passenger_${n}_gender`, t.gender)
  }

  const checkCoupon = () => {
    const code = (formRef.current?.elements.namedItem("coupon_code") as HTMLInputElement | null)?.value.trim() ?? ""
    startCheck(async () => {
      const res = await quoteFor(tripId, seats.join(","), code)
      if (!res.ok) return setCouponNote(res.error)
      setQuote(res.quote)
      setCouponNote(code ? (res.quote.coupon_problem ?? `${res.quote.coupon} saves ${rupees(res.quote.discount)}`) : null)
    })
  }

  return (
    <form ref={formRef} action={action} className="grid gap-8 lg:grid-cols-[1fr_320px]" data-relay-form="Passenger details" aria-label="Passenger details">
      <input type="hidden" name="trip_id" value={tripId} />
      <input type="hidden" name="seats" value={seats.join(",")} />
      <input type="hidden" name="boarding_point" value={boarding} />
      <input type="hidden" name="dropping_point" value={dropping} />
      <div className="flex flex-col gap-8">
        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">Passengers</h2>
          {seats.map((seat, i) => {
            const n = i + 1
            const info = seatInfo.find((s) => s.id === seat)
            return (
              <fieldset key={seat} className="flex flex-col gap-3 rounded-xl border bg-card p-4">
                <legend className="px-1 text-sm font-medium">
                  Passenger {n} · seat {seat}
                  {info?.women_only && <span className="ml-2 text-xs font-normal text-pink-700">women only</span>}
                </legend>
                <div className="flex flex-wrap gap-1.5" data-relay-ignore>
                  {people.map((t) => (
                    <Button key={t.id} type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => fillPassenger(n, t)}>
                      <UserPlusIcon className="size-3" /> {t.id === "me" ? `Me (${t.name.split(" ")[0]})` : t.name.split(" ")[0]}
                    </Button>
                  ))}
                </div>
                <div className="grid gap-3 sm:grid-cols-[1fr_90px_140px]">
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span>
                      Full name<span className="text-destructive">*</span>
                    </span>
                    <input
                      name={`passenger_${n}_name`}
                      required
                      maxLength={60}
                      defaultValue={n === 1 ? self.name : ""}
                      aria-invalid={Boolean(err(`passenger_${n}_name`)) || undefined}
                      className={input}
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span>
                      Age<span className="text-destructive">*</span>
                    </span>
                    <input
                      name={`passenger_${n}_age`}
                      type="number"
                      min={1}
                      max={110}
                      required
                      defaultValue={n === 1 ? self.age : undefined}
                      aria-invalid={Boolean(err(`passenger_${n}_age`)) || undefined}
                      className={input}
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span>
                      Gender<span className="text-destructive">*</span>
                    </span>
                    <select name={`passenger_${n}_gender`} required defaultValue={n === 1 ? self.gender : ""} className={input}>
                      <option value="" disabled>
                        Choose
                      </option>
                      {GENDERS.map((g) => (
                        <option key={g} value={g}>
                          {g[0].toUpperCase() + g.slice(1)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {[`passenger_${n}_name`, `passenger_${n}_age`, `passenger_${n}_gender`].map(
                  (f) => err(f) && <p key={f} className="text-xs text-destructive">{err(f)}</p>,
                )}
              </fieldset>
            )
          })}
          {err("seats") && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{err("seats")}</p>}
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">Contact</h2>
          <p className="-mt-2 text-xs text-muted-foreground">The e-ticket and the bus staff&apos;s call come here.</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-sm">
              <span>
                Email<span className="text-destructive">*</span>
              </span>
              <input name="contact_email" type="email" required defaultValue={me.traveller.email} aria-invalid={Boolean(err("contact_email")) || undefined} className={input} />
              {err("contact_email") && <span className="text-xs text-destructive">{err("contact_email")}</span>}
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span>
                Mobile number<span className="text-destructive">*</span>
              </span>
              <input name="contact_phone" type="tel" required defaultValue={me.traveller.phone} aria-invalid={Boolean(err("contact_phone")) || undefined} className={input} />
              {err("contact_phone") && <span className="text-xs text-destructive">{err("contact_phone")}</span>}
            </label>
          </div>
        </section>

        <fieldset className="flex flex-col gap-3">
          <legend className="mb-3 text-lg font-semibold">Pay with</legend>
          {me.payment_methods.map((m, i) => (
            <label
              key={m.id}
              className="flex cursor-pointer items-center gap-3 rounded-xl border bg-card p-4 text-sm has-checked:border-primary has-checked:ring-1 has-checked:ring-primary"
            >
              <input type="radio" name="payment_method" value={m.id} defaultChecked={i === 0} className="accent-[var(--primary)]" />
              <span className="flex-1">{m.label}</span>
              {m.id === "wallet" && <span className="text-xs text-muted-foreground">Balance {rupees(me.wallet_balance)}</span>}
            </label>
          ))}
          {err("payment_method") && <p className="text-xs text-destructive">{err("payment_method")}</p>}
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <LockIcon className="size-3" /> Demo site: nothing is charged. {PAYMENT_METHODS.card_on_file} is a test card.
          </p>
        </fieldset>
      </div>

      <aside className="flex flex-col gap-4">
        <div className="sticky top-20 flex flex-col gap-3 rounded-2xl border bg-card p-5" data-testid="fare-summary">
          <h2 className="font-semibold">Fare</h2>
          <dl className="flex flex-col gap-1.5 text-sm">
            {quote.seats.map((s) => (
              <div key={s} className="flex justify-between">
                <dt className="text-muted-foreground">Seat {s}</dt>
                <dd className="tabular-nums">{rupees(quote.seat_prices[s])}</dd>
              </div>
            ))}
            {quote.discount > 0 && (
              <div className="flex justify-between text-emerald-700">
                <dt>Offer {quote.coupon}</dt>
                <dd className="tabular-nums">−{rupees(quote.discount)}</dd>
              </div>
            )}
            {quote.gst > 0 && (
              <div className="flex justify-between">
                <dt className="text-muted-foreground">GST 5%</dt>
                <dd className="tabular-nums">{rupees(quote.gst)}</dd>
              </div>
            )}
            <div className="mt-1 flex justify-between border-t pt-2 text-base font-semibold">
              <dt>Total</dt>
              <dd className="tabular-nums">{rupees(quote.total)}</dd>
            </div>
          </dl>
          <label className="flex flex-col gap-1.5 text-sm">
            Offer code (optional)
            <span className="flex gap-2">
              <input name="coupon_code" className={`${input} h-9 uppercase`} placeholder="WAYLINE10" aria-invalid={Boolean(err("coupon_code")) || undefined} />
              <Button type="button" variant="outline" size="sm" className="h-9" onClick={checkCoupon} disabled={checking}>
                Apply
              </Button>
            </span>
          </label>
          {(couponNote || err("coupon_code")) && <p className="text-xs text-muted-foreground">{err("coupon_code") ?? couponNote}</p>}
          {state?.error && !state.fields && (
            <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {state.error}
            </p>
          )}
          {state?.fields && <p className="text-xs text-destructive" role="alert">{state.error} — see the highlighted fields.</p>}
          <Button type="submit" size="lg" disabled={pending} data-testid="pay">
            {pending && <Loader2Icon className="animate-spin" />}
            Pay {rupees(quote.total)}
          </Button>
        </div>
      </aside>
    </form>
  )
}
