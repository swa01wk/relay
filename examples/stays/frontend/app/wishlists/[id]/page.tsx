import Link from "next/link"
import { notFound } from "next/navigation"
import { ChevronLeftIcon } from "lucide-react"

import { ListingCard } from "@/components/stays/listing-card"
import { ScreenState } from "@/components/stays/screen-state"
import { stays, StaysError } from "@/lib/stays"
import type { Wishlist } from "@/lib/types"

export default async function WishlistPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  let w: Omit<Wishlist, "count">
  try {
    w = (await stays<{ wishlist: Omit<Wishlist, "count"> }>(`/api/wishlists/${encodeURIComponent(decodeURIComponent(id))}`)).wishlist
  } catch (e) {
    if (e instanceof StaysError && e.status === 404) notFound()
    throw e
  }
  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="wishlist" value={{ wishlist_id: w.id, name: w.name, homes: w.listings.map((l) => `${l.id} ${l.title}`) }} />
      <Link href="/wishlists" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeftIcon className="size-4" /> Wishlists
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">{w.name}</h1>
      {w.listings.length ? (
        <div className="grid gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
          {w.listings.map((l) => (
            <ListingCard key={l.id} listing={l} saved />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Nothing saved yet — tap the heart on any home.</p>
      )}
    </div>
  )
}
