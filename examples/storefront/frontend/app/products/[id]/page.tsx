import Link from "next/link"
import { notFound } from "next/navigation"
import { CheckIcon, TruckIcon, Undo2Icon } from "lucide-react"

import { ProductArt } from "@/components/shop/product-art"
import { ProductGrid } from "@/components/shop/product-card"
import { ProductPurchase } from "@/components/shop/product-purchase"
import { ProductTabs } from "@/components/shop/product-tabs"
import { Price, StockBadge } from "@/components/shop/price"
import { Rating } from "@/components/shop/rating"
import { ReviewForm } from "@/components/shop/review-form"
import { ScreenState } from "@/components/shop/screen-state"
import { shortDate } from "@/lib/format"
import { shop, ShopError } from "@/lib/shop"
import type { ProductDetail } from "@/lib/types"

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  let data: ProductDetail
  try {
    data = await shop<ProductDetail>(`/api/products/${encodeURIComponent(id)}`)
  } catch (e) {
    if (e instanceof ShopError && e.status === 404) notFound()
    throw e
  }
  const p = data.product
  const total = Object.values(data.rating_breakdown).reduce((a, b) => a + b, 0) || 1

  return (
    <div className="flex flex-col gap-12">
      <ScreenState
        name="product_page"
        value={{ id: p.id, name: p.name, price: p.price, stock: p.stock, in_cart: data.in_cart_quantity, in_wishlist: data.in_wishlist, can_review: data.can_review }}
      />
      <nav className="text-sm text-muted-foreground" aria-label="Breadcrumb">
        <Link href="/products" className="hover:underline">
          Shop
        </Link>{" "}
        /{" "}
        <Link href={`/products?category=${encodeURIComponent(p.category)}`} className="hover:underline">
          {p.category}
        </Link>
      </nav>
      <div className="grid gap-8 md:grid-cols-2 lg:gap-14">
        <div className="relative">
          <ProductArt hue={p.hue} category={p.category} className="rounded-3xl" iconClassName="size-1/4" />
          {p.on_sale && <span className="sale-badge absolute top-4 left-4 rounded-full px-3 py-1 text-sm font-semibold">−{p.discount_pct}%</span>}
        </div>
        <div className="flex flex-col gap-5">
          <div>
            <p className="text-sm text-muted-foreground">{p.brand}</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight text-balance">{p.name}</h1>
            <a href="#product-tabs" className="mt-2 inline-block">
              <Rating value={p.rating} count={p.review_count} />
            </a>
          </div>
          <div className="flex flex-col gap-1">
            <Price price={p.price} compareAt={p.compare_at_price} className="text-2xl" />
            <StockBadge status={p.stock_status} stock={p.stock} />
          </div>
          <p className="text-pretty text-muted-foreground">{p.summary}</p>
          <ProductPurchase productId={p.id} name={p.name} stock={p.stock} inCart={data.in_cart_quantity ?? 0} saved={data.in_wishlist ?? false} />
          <ul className="flex flex-col gap-2 border-t pt-5 text-sm">
            <li className="flex items-center gap-2">
              <TruckIcon className="size-4 text-primary" /> Free standard shipping on orders over $75
            </li>
            <li className="flex items-center gap-2">
              <Undo2Icon className="size-4 text-primary" /> Free returns within 30 days of delivery
            </li>
          </ul>
        </div>
      </div>

      <ProductTabs
        reviewCount={p.review_count}
        details={
          <ul className="grid gap-2 sm:grid-cols-2">
            {p.features.map((f) => (
              <li key={f} className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm">
                <CheckIcon className="size-4 text-primary" /> {f}
              </li>
            ))}
            <li className="rounded-lg border bg-card px-3 py-2 text-sm text-muted-foreground">
              {p.sold_last_30d} sold in the last 30 days · item {p.id}
            </li>
          </ul>
        }
        reviews={
          <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
            <div className="flex flex-col gap-2 text-sm">
              <Rating value={p.rating} count={p.review_count} className="text-base" />
              {Object.entries(data.rating_breakdown).map(([stars, n]) => (
                <div key={stars} className="flex items-center gap-2">
                  <span className="w-12 text-muted-foreground">{stars} star</span>
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                    <span className="block h-full rounded-full bg-amber-400" style={{ width: `${(n / total) * 100}%` }} />
                  </span>
                  <span className="w-5 text-right tabular-nums text-muted-foreground">{n}</span>
                </div>
              ))}
            </div>
            <div className="flex flex-col gap-5">
              {data.can_review && <ReviewForm productId={p.id} />}
              {data.reviews.map((r) => (
                <article key={r.id} className="border-b pb-5 last:border-0">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <Rating value={r.rating} className="text-xs" />
                    <span className="font-medium">{r.title}</span>
                  </div>
                  <p className="mt-2 text-sm">{r.body}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {r.author} · {shortDate(r.created_at)}
                  </p>
                </article>
              ))}
            </div>
          </div>
        }
      />

      {data.related.length > 0 && (
        <section>
          <h2 className="mb-5 text-xl font-semibold tracking-tight">More in {p.category}</h2>
          <ProductGrid products={data.related} />
        </section>
      )}
    </div>
  )
}
