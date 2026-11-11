import { Suspense } from "react"
import Link from "next/link"

import { CatalogFilters, SortSelect } from "@/components/shop/catalog-filters"
import { ProductGrid } from "@/components/shop/product-card"
import { ScreenState } from "@/components/shop/screen-state"
import { shop } from "@/lib/shop"
import type { ProductCard } from "@/lib/types"

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> }

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)

export default async function CatalogPage({ searchParams }: Props) {
  const sp = await searchParams
  const filters = {
    query: one(sp.query),
    category: one(sp.category),
    brand: one(sp.brand),
    min_price: one(sp.min_price),
    max_price: one(sp.max_price),
    min_rating: one(sp.min_rating),
    in_stock: one(sp.in_stock) ? true : undefined,
    on_sale: one(sp.on_sale) ? true : undefined,
    sort_by: one(sp.sort_by),
  }
  const { products, total } = await shop<{ products: ProductCard[]; total: number }>("/api/products", {
    query: { ...filters, limit: 60 },
  })
  const title = filters.on_sale ? "Deals" : filters.category ?? (filters.query ? `Results for “${filters.query}”` : "All products")
  const applied = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== undefined))

  return (
    <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
      <ScreenState
        name="catalog"
        value={{ filters: applied, rows_shown: products.length, total, visible: products.slice(0, 24).map((p) => `${p.id} ${p.name} $${p.price}`) }}
      />
      <Suspense>
        <CatalogFilters />
      </Suspense>
      <section className="flex flex-col gap-6" aria-label="Products" data-testid="catalog">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            <p className="text-sm text-muted-foreground">
              {total} product{total === 1 ? "" : "s"}
            </p>
          </div>
          <Suspense>
            <SortSelect />
          </Suspense>
        </div>
        {products.length ? (
          <ProductGrid products={products} />
        ) : (
          <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
            Nothing matches these filters. <Link href="/products" className="text-primary underline">Clear them</Link> or ask the assistant.
          </div>
        )}
      </section>
    </div>
  )
}
