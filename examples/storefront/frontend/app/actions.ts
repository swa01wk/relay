"use server"

/**
 * The store's writes (server actions). Each calls the store API — the same logic the assistant's
 * side-effecting tools run — and refreshes the page. Inventory: examples/storefront/relay-tools.md.
 */
import { refresh, revalidatePath } from "next/cache"
import { redirect } from "next/navigation"

import { shop, ShopError } from "@/lib/shop"
import type { Order } from "@/lib/types"

export type ActionResult = { ok: boolean; error?: string; fields?: Record<string, string> }

async function run(fn: () => Promise<unknown>): Promise<ActionResult> {
  try {
    await fn()
  } catch (e) {
    if (e instanceof ShopError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  refresh()
  return { ok: true }
}

export async function addToCart(productId: string, quantity = 1) {
  return run(() => shop("/api/cart/items", { method: "POST", body: { product_id: productId, quantity } }))
}

export async function updateCartItem(productId: string, quantity: number) {
  return run(() => shop(`/api/cart/items/${productId}`, { method: "PATCH", body: { quantity } }))
}

export async function removeFromCart(productId: string) {
  return run(() => shop(`/api/cart/items/${productId}`, { method: "DELETE" }))
}

export async function clearCart() {
  return run(() => shop("/api/cart", { method: "DELETE" }))
}

export async function applyCoupon(_prev: ActionResult | null, form: FormData) {
  return run(() => shop("/api/cart/coupon", { method: "POST", body: { code: String(form.get("code") ?? "") } }))
}

export async function removeCoupon() {
  return run(() => shop("/api/cart/coupon", { method: "DELETE" }))
}

export async function toggleWishlist(productId: string, saved: boolean) {
  return run(() =>
    saved
      ? shop(`/api/wishlist/${productId}`, { method: "DELETE" })
      : shop("/api/wishlist", { method: "POST", body: { product_id: productId } }),
  )
}

export async function placeOrder(_prev: ActionResult | null, form: FormData): Promise<ActionResult> {
  let order: Order
  try {
    order = (await shop<{ order: Order }>("/api/checkout", { method: "POST", body: Object.fromEntries(form) })).order
  } catch (e) {
    if (e instanceof ShopError) return { ok: false, error: e.message, fields: e.fields }
    throw e
  }
  revalidatePath("/", "layout") // the header's cart count
  redirect(`/orders/${order.id}?placed=1`)
}

export async function cancelOrder(orderId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => shop(`/api/orders/${orderId}/cancel`, { method: "POST", body: { reason: form.get("reason") } }))
}

export async function requestReturn(orderId: string, _prev: ActionResult | null, form: FormData) {
  return run(() =>
    shop(`/api/orders/${orderId}/return`, { method: "POST", body: { reason: form.get("reason"), notes: form.get("notes") || null } }),
  )
}

export async function updateOrderAddress(orderId: string, _prev: ActionResult | null, form: FormData) {
  return run(() => shop(`/api/orders/${orderId}/address`, { method: "PATCH", body: Object.fromEntries(form) }))
}

export async function reorder(orderId: string) {
  const result = await run(() => shop(`/api/orders/${orderId}/reorder`, { method: "POST" }))
  if (result.ok) {
    revalidatePath("/", "layout")
    redirect("/cart")
  }
  return result
}

export async function writeReview(productId: string, _prev: ActionResult | null, form: FormData) {
  return run(() =>
    shop(`/api/products/${productId}/reviews`, {
      method: "POST",
      body: { rating: Number(form.get("rating")), title: form.get("title"), body: form.get("body") },
    }),
  )
}
