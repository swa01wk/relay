import Link from "next/link"
import { redirect } from "next/navigation"

import { CheckoutForm } from "@/components/shop/checkout-form"
import { OrderSummary } from "@/components/shop/order-summary"
import { ScreenState } from "@/components/shop/screen-state"
import { money } from "@/lib/format"
import { shop } from "@/lib/shop"
import type { Cart, ShopperContext } from "@/lib/types"

type ShippingOptions = { options: { method: string; label: string; cost: number; order_total: number }[] }

export default async function CheckoutPage() {
  const [cart, me, shipping] = await Promise.all([
    shop<Cart>("/api/cart"),
    shop<ShopperContext>("/api/me"),
    shop<ShippingOptions>("/api/shipping-options"),
  ])
  if (!cart.items.length) redirect("/cart")
  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_380px]">
      <ScreenState name="checkout" value={{ total: cart.total, items: cart.item_count, shipping_options: shipping.options }} />
      <div className="flex flex-col gap-6">
        <div>
          <Link href="/cart" className="text-sm text-muted-foreground hover:underline">
            ← Back to cart
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Checkout</h1>
        </div>
        <CheckoutForm address={me.shopper.default_address} email={me.shopper.email} shippingCosts={shipping.options} payments={me.payment_methods} />
      </div>
      <aside className="flex flex-col gap-4 lg:sticky lg:top-32 lg:self-start">
        <ul className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-sm">
          {cart.items.map((i) => (
            <li key={i.product_id} className="flex justify-between gap-3">
              <span>
                {i.quantity} × {i.name}
              </span>
              <span className="tabular-nums">{money(i.line_total)}</span>
            </li>
          ))}
        </ul>
        <OrderSummary {...cart} coupon={cart.coupon?.code} />
        <p className="text-xs text-muted-foreground">Shipping shown for standard delivery; express is added if you choose it.</p>
      </aside>
    </div>
  )
}
