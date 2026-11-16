/** Shapes returned by the store API (examples/storefront/tools). */

export type StockStatus = "in_stock" | "low_stock" | "out_of_stock"

export type ProductCard = {
  id: string
  name: string
  category: string
  brand: string
  price: number
  compare_at_price: number | null
  on_sale: boolean
  discount_pct: number
  rating: number
  review_count: number
  stock: number
  stock_status: StockStatus
  hue: number
  summary: string
  reason?: string
}

export type Review = {
  id: string
  product_id: string
  author: string
  rating: number
  title: string
  body: string
  created_at: string
}

export type ProductDetail = {
  product: ProductCard & { features: string[]; sold_last_30d: number }
  reviews: Review[]
  rating_breakdown: Record<string, number>
  related: ProductCard[]
  in_cart_quantity?: number
  in_wishlist?: boolean
  can_review?: boolean
}

export type CartLine = {
  product_id: string
  name: string
  category: string
  hue: number
  unit_price: number
  quantity: number
  line_total: number
  stock: number
  stock_status: StockStatus
}

export type Cart = {
  items: CartLine[]
  item_count: number
  coupon: { code: string; description: string } | null
  warnings: string[]
  subtotal: number
  discount: number
  shipping: number
  shipping_method: "standard" | "express"
  tax: number
  total: number
  free_shipping_remaining: number
  coupon_note: string | null
}

export type Address = {
  full_name: string
  address_line1: string
  address_line2: string
  city: string
  state: string
  postal_code: string
  country: string
  phone: string
}

export type OrderStatus = "processing" | "shipped" | "delivered" | "cancelled" | "return_requested"

export type OrderSummary = {
  id: string
  status: OrderStatus
  placed_date: string
  total: number
  item_count: number
  estimated_delivery: [string, string]
  can_cancel: boolean
  can_return: boolean
  items: string[]
}

export type Order = {
  id: string
  status: OrderStatus
  placed_at: string
  placed_date: string
  items: Omit<CartLine, "stock" | "stock_status">[]
  coupon: string | null
  subtotal: number
  discount: number
  shipping: number
  tax: number
  total: number
  item_count: number
  shipping_method: "standard" | "express"
  estimated_delivery: [string, string]
  shipping_address: Address
  email: string
  payment_label: string
  gift_note: string
  carrier: string | null
  tracking_number: string | null
  timeline: { status: string; at: string; carrier?: string | null; tracking_number?: string | null; reason?: string | null }[]
  can_cancel: boolean
  can_change_address: boolean
  can_return: boolean
  return_window_ends: string | null
  return: { reason: string; notes: string; requested_at: string; label: string; refund_amount: number } | null
}

export type ShopperContext = {
  shopper: { name: string; email: string; default_address: Address }
  cart_items: number
  wishlist_items: number
  orders: number
  open_orders: number
  lifetime_spend: number
  payment_methods: Record<string, string>
}

export type Category = {
  category: string
  product_count: number
  min_price: number
  max_price: number
  on_sale: number
  brands: string[]
}

export const CATEGORIES = ["Audio", "Home Office", "Kitchen", "Outdoor", "Wellness", "Accessories"] as const
export const BRANDS = ["Oakline", "Northpeak", "Sonora", "Hearth & Co", "Fieldwork", "Calma"] as const
export const SORTS = {
  featured: "Featured",
  best_selling: "Best selling",
  rating: "Top rated",
  price: "Price: low to high",
  discount: "Biggest discount",
  newest: "Newest",
} as const
export const COUNTRIES = ["United States", "Canada", "United Kingdom", "Germany", "India", "Australia"] as const
export const CANCEL_REASONS = {
  changed_my_mind: "Changed my mind",
  found_a_better_price: "Found a better price",
  ordered_by_mistake: "Ordered by mistake",
  delivery_too_slow: "Delivery too slow",
  other: "Other",
} as const
export const RETURN_REASONS = {
  damaged: "Arrived damaged",
  wrong_item: "Wrong item",
  not_as_described: "Not as described",
  no_longer_needed: "No longer needed",
  other: "Other",
} as const
