import { notFound } from "next/navigation"
import { AwardIcon, CalendarCheckIcon, CheckIcon, DoorOpenIcon, StarIcon, XIcon, ZapIcon } from "lucide-react"

import { BookingPanel } from "@/components/stays/booking-panel"
import { ListingArt } from "@/components/stays/listing-art"
import { SaveButton } from "@/components/stays/save-button"
import { ScreenState } from "@/components/stays/screen-state"
import { stays, StaysError } from "@/lib/stays"
import { rupees } from "@/lib/format"
import { POLICY_LABEL, SUB_RATINGS, type ListingDetail } from "@/lib/types"

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)
const num = (v: string | undefined) => (v === undefined || v === "" ? undefined : Number(v))

export default async function ListingPage({ params, searchParams }: Props) {
  const [{ id }, sp] = await Promise.all([params, searchParams])
  let l: ListingDetail
  try {
    l = (await stays<{ listing: ListingDetail }>(`/api/listings/${id}`)).listing
  } catch (e) {
    if (e instanceof StaysError && e.status === 404) notFound()
    throw e
  }
  const initial = {
    check_in: one(sp.check_in),
    check_out: one(sp.check_out),
    adults: num(one(sp.adults)),
    children: num(one(sp.children)),
    infants: num(one(sp.infants)),
    pets: num(one(sp.pets)),
  }
  const rules = l.house_rules

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="listing"
        value={{ listing_id: l.id, title: l.title, price: l.price, min_nights: l.min_nights, instant_book: l.instant_book, policy: l.cancellation_policy, saved_in: l.saved_in_wishlists }}
      />
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{l.title}</h1>
          <p className="flex flex-wrap items-center gap-x-2 text-sm">
            {l.review_count > 0 && (
              <span className="flex items-center gap-1 font-medium">
                <StarIcon className="size-3.5 fill-current" /> {l.rating.toFixed(2)} · {l.review_count} reviews
              </span>
            )}
            {l.host.superhost && <span>· Superhost</span>}
            <span className="text-muted-foreground">
              · {l.area}, {l.destination_name}
              {l.state !== l.destination_name && `, ${l.state}`}
            </span>
          </p>
        </div>
        <SaveButton listingId={l.id} saved={l.saved_in_wishlists.length > 0} withLabel className="[&_svg]:text-foreground" />
      </header>

      <div className="grid h-72 grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-2xl sm:h-96">
        <ListingArt hue={l.hue} icon={l.icon} label={l.property_type_label} className="col-span-4 row-span-2 sm:col-span-2" />
        {["Living room", "Bedroom", "View", "Outside"].map((label, i) => (
          <ListingArt key={label} hue={l.hue} icon={l.icon} shot={i + 1} label={label} className="hidden sm:grid" />
        ))}
      </div>

      <div className="grid gap-10 lg:grid-cols-[1fr_380px]">
        <div className="flex flex-col gap-8">
          <section className="flex flex-col gap-1 border-b pb-6">
            <h2 className="text-lg font-semibold">
              {l.property_type_label} hosted by {l.host.name}
            </h2>
            <p className="text-muted-foreground">
              {l.max_guests} guests · {l.bedrooms} bedroom{l.bedrooms > 1 ? "s" : ""} · {l.beds} bed{l.beds > 1 ? "s" : ""} · {l.baths} bath{l.baths > 1 ? "s" : ""}
            </p>
          </section>
          <section className="flex flex-col gap-4 border-b pb-6 text-sm">
            {l.host.superhost && (
              <p className="flex gap-3">
                <AwardIcon className="size-5 shrink-0" />
                <span>
                  <span className="font-medium">{l.host.name} is a Superhost</span>
                  <span className="block text-muted-foreground">
                    Hosting since {l.host.since}, replies {l.host.response_time} ({l.host.response_rate}%).
                  </span>
                </span>
              </p>
            )}
            <p className="flex gap-3">
              {l.instant_book ? <ZapIcon className="size-5 shrink-0" /> : <CalendarCheckIcon className="size-5 shrink-0" />}
              <span>
                <span className="font-medium">{l.instant_book ? "Instant book" : "Request to book"}</span>
                <span className="block text-muted-foreground">
                  {l.instant_book ? "Confirmed as soon as you pay." : `${l.host.name} reviews each request; you're charged only if it's accepted.`}
                </span>
              </span>
            </p>
            <p className="flex gap-3">
              <DoorOpenIcon className="size-5 shrink-0" />
              <span>
                <span className="font-medium">{POLICY_LABEL[l.cancellation_policy]} cancellation</span>
                <span className="block text-muted-foreground">{l.cancellation_policy_text}</span>
              </span>
            </p>
          </section>
          <section className="border-b pb-6">
            <p className="leading-relaxed">{l.description}</p>
          </section>
          <section className="flex flex-col gap-3 border-b pb-6">
            <h2 className="text-lg font-semibold">What this place offers</h2>
            <ul className="grid gap-2 text-sm sm:grid-cols-2">
              {l.amenity_labels.map((a) => (
                <li key={a} className="flex items-center gap-2">
                  <CheckIcon className="size-4 text-primary" /> {a}
                </li>
              ))}
            </ul>
          </section>
          <section className="flex flex-col gap-3 border-b pb-6 text-sm">
            <h2 className="text-lg font-semibold">House rules and fees</h2>
            <ul className="grid gap-2 sm:grid-cols-2">
              <li>Check-in from {rules.check_in_from}</li>
              <li>Check-out by {rules.check_out_by}</li>
              <li>Up to {rules.max_guests} guests</li>
              <li className="flex items-center gap-1.5">{rules.pets_allowed ? <CheckIcon className="size-4" /> : <XIcon className="size-4" />} Pets{l.pet_fee ? ` (${rupees(l.pet_fee)} per stay)` : ""}</li>
              <li className="flex items-center gap-1.5">{rules.events_allowed ? <CheckIcon className="size-4" /> : <XIcon className="size-4" />} Events</li>
              <li className="flex items-center gap-1.5">{rules.smoking_allowed ? <CheckIcon className="size-4" /> : <XIcon className="size-4" />} Smoking</li>
              <li>Weekend nights {rupees(l.weekend_price)}</li>
              {l.cleaning_fee > 0 && <li>Cleaning fee {rupees(l.cleaning_fee)}</li>}
              {l.extra_guest_fee > 0 && <li>{rupees(l.extra_guest_fee)} a night per guest after {l.guests_included}</li>}
              {l.weekly_discount > 0 && <li>{l.weekly_discount}% off 7+ nights</li>}
              <li>{l.monthly_discount}% off 28+ nights</li>
              <li>Minimum stay {l.min_nights} night{l.min_nights > 1 ? "s" : ""}</li>
            </ul>
          </section>
          <section className="flex flex-col gap-4" aria-label="Reviews">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <StarIcon className="size-4 fill-current" /> {l.rating.toFixed(2)} · {l.review_count} reviews
            </h2>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-3">
              {Object.entries(SUB_RATINGS).map(([k, label]) => (
                <div key={k} className="flex items-center justify-between gap-3">
                  <dt>{label}</dt>
                  <dd className="font-medium tabular-nums">{l.rating_breakdown[k as keyof typeof SUB_RATINGS]?.toFixed(1)}</dd>
                </div>
              ))}
            </dl>
            <div className="grid gap-5 sm:grid-cols-2">
              {l.reviews.map((r) => (
                <article key={r.id} className="text-sm">
                  <p className="font-medium">
                    {r.author}
                    {r.mine && <span className="ml-2 text-xs text-primary">You</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {"★".repeat(r.rating)} · {r.date}
                  </p>
                  <p className="mt-1">{r.comment}</p>
                </article>
              ))}
            </div>
          </section>
        </div>
        <BookingPanel listing={l} initial={initial} />
      </div>
    </div>
  )
}
