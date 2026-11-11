import Link from "next/link"
import { HeartIcon } from "lucide-react"

import { WishlistButton } from "@/components/shop/cart-buttons"
import { ProductCard } from "@/components/shop/product-card"
import { ScreenState } from "@/components/shop/screen-state"
import { Button } from "@/components/ui/button"
import { shop } from "@/lib/shop"
import type { ProductCard as Product } from "@/lib/types"

export default async function WishlistPage() {
  const { products } = await shop<{ products: Product[] }>("/api/wishlist")
  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="wishlist" value={{ products: products.map((p) => `${p.id} ${p.name}${p.on_sale ? " (on sale)" : ""}`) }} />
      <h1 className="text-2xl font-semibold tracking-tight">Wishlist</h1>
      {products.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed py-14 text-sm text-muted-foreground">
          <HeartIcon className="size-8" />
          Nothing saved yet.
          <Button asChild variant="outline">
            <Link href="/products">Browse products</Link>
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 gap-y-8 md:grid-cols-3 xl:grid-cols-4">
          {products.map((p) => (
            <div key={p.id} className="relative">
              <ProductCard product={p} />
              <div className="absolute top-2 right-2">
                <WishlistButton productId={p.id} saved />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
