import Link from "next/link"
import { PackageIcon } from "lucide-react"

import { OrderStatus } from "@/components/shop/order-status"
import { ScreenState } from "@/components/shop/screen-state"
import { money, shortDate, statusLabel } from "@/lib/format"
import { shop } from "@/lib/shop"
import type { OrderSummary } from "@/lib/types"

const FILTERS = ["processing", "shipped", "delivered", "return_requested", "cancelled"] as const

export default async function OrdersPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const { status } = await searchParams
  const { orders, total } = await shop<{ orders: OrderSummary[]; total: number }>("/api/orders", { query: { status } })
  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="orders" value={{ status: status ?? "all", rows_shown: orders.length, orders: orders.map((o) => `${o.id} ${o.status} ${money(o.total)}`) }} />
      <h1 className="text-2xl font-semibold tracking-tight">Your orders</h1>
      <nav className="flex flex-wrap gap-2 text-sm" aria-label="Filter orders">
        {[undefined, ...FILTERS].map((s) => (
          <Link
            key={s ?? "all"}
            href={s ? `/orders?status=${s}` : "/orders"}
            aria-current={status === s ? "page" : undefined}
            className="rounded-full border px-3 py-1 text-muted-foreground aria-[current=page]:border-primary aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground"
          >
            {s ? statusLabel(s) : "All"}
          </Link>
        ))}
      </nav>
      {orders.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed py-14 text-sm text-muted-foreground">
          <PackageIcon className="size-8" />
          No {status ? statusLabel(status).toLowerCase() : ""} orders.
        </div>
      ) : (
        <ul className="flex flex-col gap-3" data-testid="orders-list">
          {orders.map((o) => (
            <li key={o.id}>
              <Link href={`/orders/${o.id}`} className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border bg-card p-5 transition-colors hover:border-primary/50">
                <div className="flex min-w-40 flex-col">
                  <span className="font-mono text-sm font-medium">{o.id}</span>
                  <span className="text-xs text-muted-foreground">Placed {shortDate(o.placed_date)}</span>
                </div>
                <OrderStatus status={o.status} />
                <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{o.items.join(", ")}</span>
                <span className="font-semibold tabular-nums">{money(o.total)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{total} order{total === 1 ? "" : "s"}</p>
    </div>
  )
}
