"use client"

import { useRouter } from "next/navigation"

import { useRelayAction } from "@/components/relay/relay-provider"
import { BRANDS, CATEGORIES, SORTS } from "@/lib/types"

const FILTER_KEYS = ["query", "category", "brand", "min_price", "max_price", "min_rating", "in_stock", "on_sale", "sort_by"] as const

/**
 * Screen actions available on every page (the assistant changes the store's own screens instead of
 * drawing copies of them). Page-specific ones live on their pages.
 */
export function StoreActions() {
  const router = useRouter()

  useRelayAction(
    "FILTER_PRODUCTS",
    (params) => {
      const onCatalog = window.location.pathname === "/products"
      const next = new URLSearchParams(onCatalog && !params.reset ? window.location.search : "")
      for (const key of FILTER_KEYS) {
        if (!(key in params)) continue
        const value = params[key]
        if (value === null || value === "" || value === false) next.delete(key)
        else next.set(key, value === true ? "1" : String(value))
      }
      router.push(`/products${next.size ? `?${next}` : ""}`)
      return { applied: Object.fromEntries(next), page: "/products" }
    },
    {
      description:
        "Show the store's catalog page filtered and sorted (always prefer this over drawing a product list). Keeps the filters already applied unless reset is true; null clears one filter. Returns the filters now applied.",
      parameters: {
        type: "object",
        properties: {
          query: { type: ["string", "null"], description: "Search words" },
          category: { type: ["string", "null"], enum: [...CATEGORIES, null] },
          brand: { type: ["string", "null"], enum: [...BRANDS, null] },
          min_price: { type: ["number", "null"], description: "USD" },
          max_price: { type: ["number", "null"], description: "USD" },
          min_rating: { type: ["number", "null"], description: "1–5 stars" },
          in_stock: { type: ["boolean", "null"] },
          on_sale: { type: ["boolean", "null"] },
          sort_by: { type: ["string", "null"], enum: [...Object.keys(SORTS), null] },
          reset: { type: "boolean", description: "Clear every filter first" },
        },
      },
    },
  )

  useRelayAction(
    "OPEN_PRODUCT",
    (params) => {
      const id = String(params.product_id ?? "").toUpperCase()
      if (!/^SKU-\d+$/.test(id)) throw new Error("product_id must look like SKU-1001")
      router.push(`/products/${id}`)
      return { opened: id }
    },
    {
      description: "Open a product's page (details, reviews, add to cart).",
      parameters: {
        type: "object",
        properties: { product_id: { type: "string", description: "Product id like SKU-1001" } },
        required: ["product_id"],
      },
    },
  )

  useRelayAction(
    "OPEN_ORDER",
    (params) => {
      const id = String(params.order_id ?? "").toUpperCase()
      if (!/^ORD-\d+$/.test(id)) throw new Error("order_id must look like ORD-10423")
      router.push(`/orders/${id}`)
      return { opened: id }
    },
    {
      description: "Open one of the shopper's orders (tracking, items, cancel, return, change address).",
      parameters: {
        type: "object",
        properties: { order_id: { type: "string", description: "Order id like ORD-10423" } },
        required: ["order_id"],
      },
    },
  )

  useRelayAction(
    "FILTER_ORDERS",
    (params) => {
      const status = params.status ? String(params.status) : ""
      router.push(`/orders${status ? `?status=${status}` : ""}`)
      return { status: status || "all" }
    },
    {
      description: "Show the shopper's order list, optionally only one status; null shows all.",
      parameters: {
        type: "object",
        properties: {
          status: { type: ["string", "null"], enum: ["processing", "shipped", "delivered", "cancelled", "return_requested", null] },
        },
      },
    },
  )

  return null
}
