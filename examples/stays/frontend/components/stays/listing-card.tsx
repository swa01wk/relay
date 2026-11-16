import Link from "next/link"
import { StarIcon, ZapIcon } from "lucide-react"

import { ListingArt } from "@/components/stays/listing-art"
import { SaveButton } from "@/components/stays/save-button"
import { rupees } from "@/lib/format"
import type { ListingCard as Listing } from "@/lib/types"

export function ListingCard({ listing, saved, query = "" }: { listing: Listing; saved: boolean; query?: string }) {
  return (
    <article className="group flex flex-col gap-2" data-testid="listing-card" data-listing-id={listing.id}>
      <Link href={`/listings/${listing.id}${query}`} className="relative block overflow-hidden rounded-2xl">
        <ListingArt hue={listing.hue} icon={listing.icon} label={listing.property_type_label} className="aspect-[4/3.2] transition group-hover:scale-[1.02]" />
        {listing.superhost && <span className="absolute top-3 left-3 rounded-full bg-white/95 px-2.5 py-1 text-xs font-medium shadow-sm">Superhost</span>}
        <span className="absolute top-3 right-3">
          <SaveButton listingId={listing.id} saved={saved} />
        </span>
      </Link>
      <Link href={`/listings/${listing.id}${query}`} className="flex flex-col gap-0.5 text-sm">
        <span className="flex items-start justify-between gap-2">
          <span className="font-medium">
            {listing.area}, {listing.destination_name}
          </span>
          {listing.review_count > 0 ? (
            <span className="flex shrink-0 items-center gap-1">
              <StarIcon className="size-3.5 fill-current" /> {listing.rating.toFixed(2)}
            </span>
          ) : (
            <span className="text-xs">New</span>
          )}
        </span>
        <span className="line-clamp-1 text-muted-foreground">{listing.title}</span>
        <span className="text-muted-foreground">
          {listing.bedrooms} bedroom{listing.bedrooms > 1 ? "s" : ""} · {listing.max_guests} guests
          {listing.instant_book && (
            <span className="ml-1.5 inline-flex items-center gap-0.5 text-primary">
              <ZapIcon className="size-3" /> Instant
            </span>
          )}
        </span>
        <span className="mt-0.5">
          <span className="font-semibold">{rupees(listing.average_night ?? listing.price)}</span> night
          {listing.stay_total !== undefined && (
            <span className="text-muted-foreground">
              {" "}
              · {rupees(listing.stay_total)} total for {listing.nights}
            </span>
          )}
        </span>
      </Link>
    </article>
  )
}
