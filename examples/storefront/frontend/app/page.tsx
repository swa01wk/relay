import Link from "next/link"
import { ArrowRightIcon, MicIcon, ShieldCheckIcon, TruckIcon } from "lucide-react"

import { ProductArt } from "@/components/shop/product-art"
import { ProductGrid } from "@/components/shop/product-card"
import { ScreenState } from "@/components/shop/screen-state"
import { Button } from "@/components/ui/button"
import { money } from "@/lib/format"
import { shop } from "@/lib/shop"
import type { Category, ProductCard } from "@/lib/types"

const CATEGORY_HUES: Record<string, number> = { Audio: 250, "Home Office": 70, Kitchen: 30, Outdoor: 150, Wellness: 320, Accessories: 200 }

export default async function HomePage() {
  const [{ categories }, deals, best, picks] = await Promise.all([
    shop<{ categories: Category[] }>("/api/categories"),
    shop<{ products: ProductCard[] }>("/api/products", { query: { on_sale: true, sort_by: "discount", limit: 4 } }),
    shop<{ products: ProductCard[] }>("/api/products", { query: { sort_by: "best_selling", limit: 4 } }),
    shop<{ products: ProductCard[] }>("/api/recommendations", { query: { limit: 4 } }),
  ])
  return (
    <div className="flex flex-col gap-14">
      <ScreenState name="screen" value={{ name: "home", sections: ["categories", "deals", "best sellers", "picked for you"] }} />
      <section className="relative overflow-hidden rounded-3xl bg-primary px-6 py-12 text-primary-foreground sm:px-12 sm:py-16">
        <div className="relative z-10 max-w-xl">
          <p className="text-sm font-medium opacity-80">New season · up to 20% off</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">Good things for home, desk and trail.</h1>
          <p className="mt-4 max-w-md text-pretty opacity-85">
            Shop the way you&apos;d ask a friend: tell the assistant what you need — &ldquo;a quiet kettle under $100&rdquo; — and it
            finds it, compares it and fills your cart for you to approve.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" variant="secondary" asChild>
              <Link href="/products">
                Shop all products <ArrowRightIcon />
              </Link>
            </Button>
            <Button size="lg" variant="ghost" className="text-primary-foreground hover:bg-white/10 hover:text-primary-foreground" asChild>
              <Link href="/products?on_sale=1">See the deals</Link>
            </Button>
          </div>
        </div>
        <div className="pointer-events-none absolute -top-10 -right-16 hidden size-96 rounded-full bg-white/10 sm:block" />
        <div className="pointer-events-none absolute right-24 -bottom-24 hidden size-64 rounded-full bg-white/10 sm:block" />
      </section>

      <section className="grid gap-4 text-sm sm:grid-cols-3">
        {[
          { icon: TruckIcon, title: "Free shipping over $75", body: "Standard delivery in 3–5 business days." },
          { icon: ShieldCheckIcon, title: "30-day returns", body: "Changed your mind? Start a return from your orders." },
          { icon: MicIcon, title: "Ask, don't search", body: "Speak or type to the assistant — it works the store for you." },
        ].map(({ icon: Icon, title, body }) => (
          <div key={title} className="flex gap-3 rounded-xl border bg-card p-4">
            <Icon className="mt-0.5 size-5 shrink-0 text-primary" />
            <div>
              <p className="font-medium">{title}</p>
              <p className="text-muted-foreground">{body}</p>
            </div>
          </div>
        ))}
      </section>

      <section>
        <h2 className="text-xl font-semibold tracking-tight">Shop by category</h2>
        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {categories.map((c) => (
            <Link key={c.category} href={`/products?category=${encodeURIComponent(c.category)}`} className="group flex flex-col gap-2">
              <ProductArt hue={CATEGORY_HUES[c.category] ?? 100} category={c.category} className="transition-transform group-hover:scale-[1.03]" />
              <span className="font-medium">{c.category}</span>
              <span className="-mt-2 text-xs text-muted-foreground">
                {c.product_count} products · from {money(c.min_price)}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <Shelf title="Deals" href="/products?on_sale=1&sort_by=discount" products={deals.products} />
      <Shelf title="Picked for you" href="/products?sort_by=rating" products={picks.products} />
      <Shelf title="Best sellers" href="/products?sort_by=best_selling" products={best.products} />
    </div>
  )
}

function Shelf({ title, href, products }: { title: string; href: string; products: ProductCard[] }) {
  if (!products.length) return null
  return (
    <section>
      <div className="mb-5 flex items-end justify-between">
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        <Link href={href} className="text-sm text-primary hover:underline">
          View all
        </Link>
      </div>
      <ProductGrid products={products} />
    </section>
  )
}
