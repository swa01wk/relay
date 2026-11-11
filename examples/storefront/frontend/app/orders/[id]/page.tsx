import Link from "next/link"
import { notFound } from "next/navigation"
import { CheckCircle2Icon, CircleIcon } from "lucide-react"

import { AddressForm, CancelOrderForm, ReorderButton, ReturnForm } from "@/components/shop/order-actions"
import { OrderStatus } from "@/components/shop/order-status"
import { OrderSummary } from "@/components/shop/order-summary"
import { ProductArt } from "@/components/shop/product-art"
import { ScreenState } from "@/components/shop/screen-state"
import { money, shortDate, statusLabel } from "@/lib/format"
import { shop, ShopError } from "@/lib/shop"
import type { Order } from "@/lib/types"

export default async function OrderPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ placed?: string }> }) {
  const [{ id }, { placed }] = await Promise.all([params, searchParams])
  let order: Order
  try {
    order = (await shop<{ order: Order }>(`/api/orders/${encodeURIComponent(id)}`)).order
  } catch (e) {
    if (e instanceof ShopError && e.status === 404) notFound()
    throw e
  }
  const steps = ["placed", "shipped", "delivered"]
  const reached = new Set(order.timeline.map((t) => t.status))
  const a = order.shipping_address

  return (
    <div className="flex flex-col gap-8">
      <ScreenState
        name="order_page"
        value={{ id: order.id, status: order.status, total: order.total, can_cancel: order.can_cancel, can_return: order.can_return, can_change_address: order.can_change_address }}
      />
      {placed && (
        <div className="flex items-center gap-3 rounded-2xl bg-accent p-5 text-accent-foreground" role="status">
          <CheckCircle2Icon className="size-6" />
          <div>
            <p className="font-semibold">Thank you — your order is placed.</p>
            <p className="text-sm">A confirmation is on its way to {order.email}.</p>
          </div>
        </div>
      )}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <Link href="/orders" className="text-sm text-muted-foreground hover:underline">
            ← All orders
          </Link>
          <h1 className="mt-2 flex items-center gap-3 text-2xl font-semibold tracking-tight">
            <span className="font-mono">{order.id}</span> <OrderStatus status={order.status} />
          </h1>
          <p className="text-sm text-muted-foreground">Placed {shortDate(order.placed_at)}</p>
        </div>
        <div className="ml-auto">
          <ReorderButton orderId={order.id} />
        </div>
      </div>

      {order.status !== "cancelled" && (
        <ol className="grid gap-4 rounded-2xl border bg-card p-5 sm:grid-cols-3" aria-label="Tracking">
          {steps.map((step) => {
            const event = order.timeline.find((t) => t.status === step)
            return (
              <li key={step} className="flex gap-3">
                {reached.has(step) ? <CheckCircle2Icon className="size-5 shrink-0 text-primary" /> : <CircleIcon className="size-5 shrink-0 text-muted-foreground/50" />}
                <div className="text-sm">
                  <p className="font-medium">{statusLabel(step)}</p>
                  <p className="text-muted-foreground">
                    {event
                      ? shortDate(event.at)
                      : step === "delivered"
                        ? `Expected ${shortDate(order.estimated_delivery[0])} – ${shortDate(order.estimated_delivery[1])}`
                        : "Not yet"}
                  </p>
                  {event?.tracking_number && (
                    <p className="font-mono text-xs text-muted-foreground">
                      {event.carrier} {event.tracking_number}
                    </p>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
      {order.return && (
        <p className="rounded-2xl bg-violet-50 p-5 text-sm text-violet-900">
          Return {order.return.label} requested {shortDate(order.return.requested_at)} ({statusLabel(order.return.reason)}). Refund of{" "}
          {money(order.return.refund_amount)} once it arrives back.
        </p>
      )}

      <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-6">
          <ul className="divide-y rounded-2xl border bg-card">
            {order.items.map((item) => (
              <li key={item.product_id} className="flex items-center gap-4 p-4">
                <Link href={`/products/${item.product_id}`} className="w-16 shrink-0">
                  <ProductArt hue={item.hue} category={item.category} />
                </Link>
                <div className="flex-1">
                  <Link href={`/products/${item.product_id}`} className="font-medium hover:underline">
                    {item.name}
                  </Link>
                  <p className="text-sm text-muted-foreground">
                    {item.quantity} × {money(item.unit_price)}
                  </p>
                </div>
                <span className="font-medium tabular-nums">{money(item.line_total)}</span>
              </li>
            ))}
          </ul>
          {order.can_cancel && <CancelOrderForm orderId={order.id} />}
          {order.can_change_address && <AddressForm orderId={order.id} address={a} />}
          {order.can_return && <ReturnForm orderId={order.id} until={order.return_window_ends && shortDate(order.return_window_ends)} />}
        </div>
        <aside className="flex flex-col gap-4">
          <OrderSummary {...order} />
          <div className="rounded-2xl border bg-card p-5 text-sm">
            <p className="font-medium">Shipping to</p>
            <p className="mt-1 text-muted-foreground">
              {a.full_name}
              <br />
              {a.address_line1}
              {a.address_line2 && (
                <>
                  <br />
                  {a.address_line2}
                </>
              )}
              <br />
              {a.city}, {a.state} {a.postal_code}
              <br />
              {a.country}
            </p>
            <p className="mt-3 font-medium">Payment</p>
            <p className="text-muted-foreground">{order.payment_label}</p>
            <p className="mt-3 font-medium">Shipping</p>
            <p className="text-muted-foreground capitalize">{order.shipping_method}</p>
            {order.gift_note && (
              <>
                <p className="mt-3 font-medium">Gift note</p>
                <p className="text-muted-foreground">{order.gift_note}</p>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
