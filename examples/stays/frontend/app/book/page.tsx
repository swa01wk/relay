import Link from "next/link"
import { notFound } from "next/navigation"
import { ChevronLeftIcon, StarIcon } from "lucide-react"

import { ConfirmForm } from "@/components/stays/confirm-form"
import { ListingArt } from "@/components/stays/listing-art"
import { ScreenState } from "@/components/stays/screen-state"
import { stays, StaysError } from "@/lib/stays"
import { dateRange, guestsLabel, rupees } from "@/lib/format"
import { POLICY_LABEL, type ListingDetail, type MyContext, type QuoteResult } from "@/lib/types"

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> }
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)

export default async function BookPage({ searchParams }: Props) {
  const sp = await searchParams
  const listingId = one(sp.listing)
  if (!listingId) notFound()
  const stay = {
    listing_id: listingId.toUpperCase(),
    check_in: one(sp.check_in) ?? "",
    check_out: one(sp.check_out) ?? "",
    adults: Number(one(sp.adults) ?? 1),
    children: Number(one(sp.children) ?? 0),
    infants: Number(one(sp.infants) ?? 0),
    pets: Number(one(sp.pets) ?? 0),
  }
  let listing: ListingDetail
  try {
    listing = (await stays<{ listing: ListingDetail }>(`/api/listings/${stay.listing_id}`)).listing
  } catch (e) {
    if (e instanceof StaysError && e.status === 404) notFound()
    throw e
  }
  const back = `/listings/${listing.id}?${new URLSearchParams({ check_in: stay.check_in, check_out: stay.check_out, adults: String(stay.adults), children: String(stay.children), infants: String(stay.infants), pets: String(stay.pets) })}`
  let result: QuoteResult
  try {
    const query = { check_in: stay.check_in, check_out: stay.check_out, adults: stay.adults, children: stay.children, infants: stay.infants, pets: stay.pets }
    result = await stays<QuoteResult>(`/api/listings/${listing.id}/quote`, { query })
  } catch (e) {
    if (!(e instanceof StaysError)) throw e
    return (
      <div className="flex flex-col gap-4">
        <Link href={back} className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ChevronLeftIcon className="size-4" /> Back to the home
        </Link>
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">{e.message}. Change the dates or guests.</p>
      </div>
    )
  }
  const me = await stays<MyContext>("/api/me")
  const q = result.quote

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="confirm_and_pay"
        value={{ ...stay, available: result.available, total: q.total, instant_book: listing.instant_book, note: "Fill the Confirm and pay page form; only the guest presses the button." }}
      />
      <Link href={back} className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeftIcon className="size-4" /> Back to the home
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">{listing.instant_book ? "Confirm and pay" : "Request to book"}</h1>
      <div className="grid gap-10 lg:grid-cols-[1fr_400px]">
        <div className="flex flex-col gap-8">
          <section className="flex flex-col gap-3 border-b pb-6">
            <h2 className="text-lg font-semibold">Your trip</h2>
            <div className="flex justify-between text-sm">
              <span>
                <span className="block font-medium">Dates</span>
                {dateRange(stay.check_in, stay.check_out)} · {q.nights} night{q.nights > 1 ? "s" : ""}
              </span>
              <Link href={back} className="font-medium underline">
                Edit
              </Link>
            </div>
            <div className="flex justify-between text-sm">
              <span>
                <span className="block font-medium">Guests</span>
                {guestsLabel(stay)}
              </span>
              <Link href={back} className="font-medium underline">
                Edit
              </Link>
            </div>
            {!result.available && (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">Some of these nights were just booked — pick other dates.</p>
            )}
          </section>
          <ConfirmForm stay={stay} total={q.total} instant={listing.instant_book} hostName={listing.host.name} me={me} />
        </div>
        <aside className="flex h-fit flex-col gap-4 rounded-2xl border bg-card p-5 lg:sticky lg:top-24">
          <div className="flex gap-3">
            <ListingArt hue={listing.hue} icon={listing.icon} className="size-24 shrink-0 rounded-xl" />
            <div className="text-sm">
              <p className="font-medium">{listing.title}</p>
              <p className="text-muted-foreground">{listing.property_type_label}</p>
              {listing.review_count > 0 && (
                <p className="mt-1 flex items-center gap-1">
                  <StarIcon className="size-3 fill-current" /> {listing.rating.toFixed(2)} ({listing.review_count})
                </p>
              )}
            </div>
          </div>
          <dl className="flex flex-col gap-1.5 border-t pt-4 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">
                {rupees(q.average_night)} × {q.nights} nights
              </dt>
              <dd className="tabular-nums">{rupees(q.accommodation)}</dd>
            </div>
            {q.extra_guest_fee > 0 && (
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Extra guests</dt>
                <dd className="tabular-nums">{rupees(q.extra_guest_fee)}</dd>
              </div>
            )}
            {q.length_discount > 0 && (
              <div className="flex justify-between text-emerald-700">
                <dt>Length-of-stay discount</dt>
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
              <dt>Total (INR)</dt>
              <dd className="tabular-nums">{rupees(q.total)}</dd>
            </div>
          </dl>
          <p className="border-t pt-4 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{POLICY_LABEL[listing.cancellation_policy]} cancellation.</span> {listing.cancellation_policy_text}
          </p>
        </aside>
      </div>
    </div>
  )
}
