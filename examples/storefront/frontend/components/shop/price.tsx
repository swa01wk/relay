import { money } from "@/lib/format"
import { cn } from "@/lib/utils"

export function Price({ price, compareAt, className }: { price: number; compareAt: number | null; className?: string }) {
  return (
    <span className={cn("inline-flex items-baseline gap-2", className)}>
      <span className={cn("font-semibold tabular-nums", compareAt && "text-[oklch(0.55_0.17_35)]")}>{money(price)}</span>
      {compareAt && <s className="text-sm text-muted-foreground tabular-nums">{money(compareAt)}</s>}
    </span>
  )
}

export function StockBadge({ status, stock }: { status: string; stock: number }) {
  if (status === "out_of_stock") return <span className="text-xs font-medium text-destructive">Out of stock</span>
  if (status === "low_stock") return <span className="text-xs font-medium text-amber-700">Only {stock} left</span>
  return <span className="text-xs text-muted-foreground">In stock</span>
}
