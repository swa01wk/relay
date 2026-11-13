import { Badge } from "@/components/ui/badge"
import { statusLabel } from "@/lib/format"
import { cn } from "@/lib/utils"

const TONE: Record<string, string> = {
  requested: "bg-amber-100 text-amber-800",
  upcoming: "bg-primary/10 text-primary",
  in_stay: "bg-emerald-100 text-emerald-800",
  completed: "bg-muted text-foreground",
  cancelled: "bg-muted text-muted-foreground",
  declined: "bg-rose-100 text-rose-800",
}

export function TripStatusBadge({ status }: { status: string }) {
  const label = status === "requested" ? "Awaiting host" : status === "in_stay" ? "Staying now" : statusLabel(status)
  return (
    <Badge variant="outline" className={cn("shrink-0 border-transparent", TONE[status])}>
      {label}
    </Badge>
  )
}
