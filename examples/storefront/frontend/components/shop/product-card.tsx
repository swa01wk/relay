import Link from "next/link"

import { AddToCartButton } from "@/components/shop/cart-buttons"
import { Price, StockBadge } from "@/components/shop/price"
import { ProductArt } from "@/components/shop/product-art"
import { Rating } from "@/components/shop/rating"
import type { ProductCard as Product } from "@/lib/types"

export function ProductCard({ product }: { product: Product }) {
  return (
    <article className="group flex flex-col gap-3" data-product-id={product.id}>
      <Link href={`/products/${product.id}`} className="relative block" aria-label={product.name}>
        <ProductArt hue={product.hue} category={product.category} className="transition-transform duration-300 group-hover:scale-[1.02]" />
        {product.on_sale && (
          <span className="sale-badge absolute top-3 left-3 rounded-full px-2 py-0.5 text-xs font-semibold">−{product.discount_pct}%</span>
        )}
      </Link>
      <div className="flex flex-1 flex-col gap-1">
        <p className="text-xs text-muted-foreground">{product.brand}</p>
        <Link href={`/products/${product.id}`} className="font-medium leading-snug hover:underline">
          {product.name}
        </Link>
        <Rating value={product.rating} count={product.review_count} className="text-xs" />
        {product.reason && <p className="text-xs text-primary">{product.reason}</p>}
        <div className="mt-auto flex flex-col gap-2 pt-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-2">
            <Price price={product.price} compareAt={product.compare_at_price} />
            <StockBadge status={product.stock_status} stock={product.stock} />
          </div>
          <AddToCartButton
            productId={product.id}
            name={product.name}
            size="sm"
            className="w-full"
            disabled={product.stock_status === "out_of_stock"}
          />
        </div>
      </div>
    </article>
  )
}

export function ProductGrid({ products }: { products: Product[] }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-8 md:grid-cols-3 xl:grid-cols-4">
      {products.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
    </div>
  )
}
