"use client"

import * as React from "react"
import { HeartIcon, Loader2Icon, MinusIcon, PlusIcon, ShoppingCartIcon, Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import { addToCart, removeFromCart, toggleWishlist, updateCartItem } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function AddToCartButton({
  productId,
  name,
  quantity = 1,
  disabled,
  size = "default",
  className,
}: {
  productId: string
  name: string
  quantity?: number
  disabled?: boolean
  size?: "default" | "sm" | "lg"
  className?: string
}) {
  const [pending, start] = React.useTransition()
  return (
    <Button
      size={size}
      className={className}
      disabled={disabled || pending}
      onClick={() =>
        start(async () => {
          const result = await addToCart(productId, quantity)
          if (result.ok) toast.success(`Added ${quantity > 1 ? `${quantity} × ` : ""}${name} to your cart`)
          else toast.error(result.error ?? "Couldn't add to cart")
        })
      }
    >
      {pending ? <Loader2Icon className="animate-spin" /> : <ShoppingCartIcon />}
      {disabled ? "Out of stock" : "Add to cart"}
    </Button>
  )
}

export function WishlistButton({ productId, saved, withLabel }: { productId: string; saved: boolean; withLabel?: boolean }) {
  const [pending, start] = React.useTransition()
  return (
    <Button
      variant="outline"
      size={withLabel ? "default" : "icon"}
      aria-label={saved ? "Remove from wishlist" : "Save to wishlist"}
      aria-pressed={saved}
      disabled={pending}
      onClick={() =>
        start(async () => {
          const result = await toggleWishlist(productId, saved)
          if (!result.ok) toast.error(result.error ?? "Couldn't update the wishlist")
        })
      }
    >
      <HeartIcon className={cn(saved && "fill-[oklch(0.62_0.17_35)] text-[oklch(0.62_0.17_35)]")} />
      {withLabel && (saved ? "Saved" : "Save")}
    </Button>
  )
}

export function QuantityStepper({ productId, quantity, max }: { productId: string; quantity: number; max: number }) {
  const [pending, start] = React.useTransition()
  const set = (next: number) =>
    start(async () => {
      const result = next < 1 ? await removeFromCart(productId) : await updateCartItem(productId, next)
      if (!result.ok) toast.error(result.error ?? "Couldn't update the cart")
    })
  return (
    <div className="inline-flex items-center rounded-lg border" aria-busy={pending}>
      <Button variant="ghost" size="icon" className="size-8" aria-label="Decrease quantity" disabled={pending} onClick={() => set(quantity - 1)}>
        {quantity <= 1 ? <Trash2Icon /> : <MinusIcon />}
      </Button>
      <span className="w-8 text-center text-sm tabular-nums" aria-live="polite">
        {quantity}
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="size-8"
        aria-label="Increase quantity"
        disabled={pending || quantity >= Math.min(max, 10)}
        onClick={() => set(quantity + 1)}
      >
        <PlusIcon />
      </Button>
    </div>
  )
}

export function RemoveButton({ productId }: { productId: string }) {
  const [pending, start] = React.useTransition()
  return (
    <Button
      variant="link"
      size="sm"
      className="h-auto px-0 text-muted-foreground"
      disabled={pending}
      onClick={() => start(async () => void (await removeFromCart(productId)))}
    >
      Remove
    </Button>
  )
}
