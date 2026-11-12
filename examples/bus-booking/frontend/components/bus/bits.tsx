import { StarIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { statusLabel } from "@/lib/format"
import { cn } from "@/lib/utils"

/** Operator logo tile: initials on the operator's colour. */
export function OperatorLogo({ name, hue, className }: { name: string; hue: number; className?: string }) {
  const initials = name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
  return (
    <span
      aria-hidden="true"
      className={cn("grid size-10 shrink-0 place-items-center rounded-lg text-sm font-semibold text-white", className)}
      style={{ background: `oklch(0.55 0.13 ${hue})` }}
    >
      {initials}
    </span>
  )
}

export function Rating({ value, className }: { value: number; className?: string }) {
  const tone = value >= 4.2 ? "bg-emerald-600" : value >= 3.6 ? "bg-amber-500" : "bg-orange-600"
  return (
    <span className={cn("inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-semibold text-white tabular-nums", tone, className)}>
      <StarIcon className="size-3 fill-current" aria-hidden="true" />
      {value.toFixed(1)}
    </span>
  )
}

const STATUS_TONE: Record<string, string> = {
  upcoming: "bg-primary/10 text-primary",
  in_transit: "bg-amber-100 text-amber-800",
  completed: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-muted text-muted-foreground",
}

export function BookingStatus({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("border-transparent", STATUS_TONE[status])}>
      {status === "in_transit" ? "On the way" : statusLabel(status)}
    </Badge>
  )
}
