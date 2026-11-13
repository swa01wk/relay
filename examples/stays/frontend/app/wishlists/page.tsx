import Link from "next/link"

import { ListingArt } from "@/components/stays/listing-art"
import { ScreenState } from "@/components/stays/screen-state"
import { CreateWishlistForm } from "@/components/stays/wishlist-forms"
import { stays } from "@/lib/stays"
import type { Wishlist } from "@/lib/types"

export default async function WishlistsPage() {
  const { wishlists } = await stays<{ wishlists: Wishlist[] }>("/api/wishlists")
  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="wishlists" value={{ lists: wishlists.map((w) => `${w.id} ${w.name} (${w.count})`) }} />
      <h1 className="text-2xl font-semibold tracking-tight">Wishlists</h1>
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {wishlists.map((w) => (
          <Link key={w.id} href={`/wishlists/${encodeURIComponent(w.id)}`} className="group flex flex-col gap-2">
            <div className="grid aspect-square grid-cols-2 grid-rows-2 gap-1 overflow-hidden rounded-2xl bg-muted">
              {w.listings.slice(0, 4).map((l, i) => (
                <ListingArt key={l.id} hue={l.hue} icon={l.icon} shot={i} className={w.listings.length === 1 ? "col-span-2 row-span-2" : ""} />
              ))}
            </div>
            <span className="font-medium">{w.name}</span>
            <span className="-mt-2 text-sm text-muted-foreground">
              {w.count} saved
            </span>
          </Link>
        ))}
      </div>
      <CreateWishlistForm />
    </div>
  )
}
