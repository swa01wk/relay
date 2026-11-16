"use client"

import * as React from "react"

import { useRelayAction } from "@/components/relay/relay-provider"
import { AddToCartButton, WishlistButton } from "@/components/shop/cart-buttons"

/** Quantity picker + Add to cart + Save, with SET_PRODUCT_QUANTITY for the assistant. */
export function ProductPurchase({
  productId,
  name,
  stock,
  inCart,
  saved,
}: {
  productId: string
  name: string
  stock: number
  inCart: number
  saved: boolean
}) {
  const max = Math.max(0, Math.min(10, stock) - inCart)
  const [quantity, setQuantity] = React.useState(1)

  useRelayAction(
    "SET_PRODUCT_QUANTITY",
    (params) => {
      const q = Math.round(Number(params.quantity))
      if (!Number.isFinite(q) || q < 1 || q > Math.max(1, max)) throw new Error(`quantity must be 1–${Math.max(1, max)}`)
      setQuantity(q)
      return { quantity: q, note: "Only the picker changed; adding to the cart still needs the shopper (or an approved add_to_cart)." }
    },
    {
      description: `Set the quantity picker on the open product page (${name}). It does not add to the cart.`,
      parameters: { type: "object", properties: { quantity: { type: "integer", minimum: 1 } }, required: ["quantity"] },
    },
  )

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm" data-relay-ignore>
          <span className="text-muted-foreground">Qty</span>
          <select
            className="h-10 rounded-md border bg-background px-3"
            value={quantity}
            disabled={max < 1}
            onChange={(e) => setQuantity(Number(e.target.value))}
          >
            {Array.from({ length: Math.max(1, max) }, (_, i) => i + 1).map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <AddToCartButton productId={productId} name={name} quantity={quantity} size="lg" disabled={max < 1} className="flex-1 sm:flex-none" />
        <WishlistButton productId={productId} saved={saved} withLabel />
      </div>
      {inCart > 0 && <p className="text-sm text-muted-foreground">{inCart} already in your cart.</p>}
    </div>
  )
}
