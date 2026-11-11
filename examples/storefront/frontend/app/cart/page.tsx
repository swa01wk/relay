import Link from "next/link"
import { ShoppingBagIcon, TriangleAlertIcon } from "lucide-react"

import { QuantityStepper, RemoveButton } from "@/components/shop/cart-buttons"
import { CouponForm } from "@/components/shop/coupon-form"
import { OrderSummary } from "@/components/shop/order-summary"
import { StockBadge } from "@/components/shop/price"
import { ProductArt } from "@/components/shop/product-art"
import { ScreenState } from "@/components/shop/screen-state"
import { Button } from "@/components/ui/button"
import { money } from "@/lib/format"
import { shop } from "@/lib/shop"
import type { Cart } from "@/lib/types"

export default async function CartPage() {
  const cart = await shop<Cart>("/api/cart")
  const screen = {
    items: cart.items.map((i) => `${i.quantity} × ${i.name} (${i.product_id}) ${money(i.line_total)}`),
    total: cart.total,
    coupon: cart.coupon?.code ?? null,
  }
  if (!cart.items.length) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
        <ScreenState name="cart" value={screen} />
        <ShoppingBagIcon className="size-10 text-muted-foreground" />
        <h1 className="text-2xl font-semibold">Your cart is empty</h1>
        <p className="text-muted-foreground">Find something you like — or ask the assistant for ideas.</p>
        <Button asChild>
          <Link href="/products">Start shopping</Link>
        </Button>
      </div>
    )
  }
  const progress = Math.min(100, ((75 - cart.free_shipping_remaining) / 75) * 100)
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <ScreenState name="cart" value={screen} />
      <section className="flex flex-col gap-5" aria-label="Cart items">
        <h1 className="text-2xl font-semibold tracking-tight">Cart ({cart.item_count})</h1>
        {cart.warnings.map((w) => (
          <p key={w} className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <TriangleAlertIcon className="size-4" /> {w}
          </p>
        ))}
        <ul className="divide-y rounded-2xl border bg-card">
          {cart.items.map((item) => (
            <li key={item.product_id} className="flex gap-4 p-4" data-product-id={item.product_id}>
              <Link href={`/products/${item.product_id}`} className="w-20 shrink-0 sm:w-24">
                <ProductArt hue={item.hue} category={item.category} />
              </Link>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <Link href={`/products/${item.product_id}`} className="font-medium hover:underline">
                  {item.name}
                </Link>
                <span className="text-sm text-muted-foreground">{money(item.unit_price)} each</span>
                <StockBadge status={item.stock_status} stock={item.stock} />
                <div className="mt-auto flex items-center gap-4 pt-2">
                  <QuantityStepper productId={item.product_id} quantity={item.quantity} max={item.stock} />
                  <RemoveButton productId={item.product_id} />
                </div>
              </div>
              <span className="font-semibold tabular-nums">{money(item.line_total)}</span>
            </li>
          ))}
        </ul>
      </section>
      <aside className="flex flex-col gap-4 lg:sticky lg:top-32 lg:self-start">
        {cart.free_shipping_remaining > 0 ? (
          <div className="flex flex-col gap-2 rounded-2xl border bg-card p-4 text-sm">
            <span>
              Add <strong>{money(cart.free_shipping_remaining)}</strong> more for free standard shipping
            </span>
            <span className="h-2 overflow-hidden rounded-full bg-muted">
              <span className="block h-full rounded-full bg-primary" style={{ width: `${progress}%` }} />
            </span>
          </div>
        ) : (
          <p className="rounded-2xl bg-accent px-4 py-3 text-sm text-accent-foreground">You&apos;ve got free shipping.</p>
        )}
        <CouponForm applied={cart.coupon} note={cart.coupon_note} />
        <OrderSummary {...cart} coupon={cart.coupon?.code}>
          <Button asChild size="lg" className="mt-2">
            <Link href="/checkout">Checkout</Link>
          </Button>
          <Link href="/products" className="text-center text-xs text-muted-foreground hover:underline">
            Continue shopping
          </Link>
        </OrderSummary>
      </aside>
    </div>
  )
}
