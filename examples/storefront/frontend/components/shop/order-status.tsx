import { Badge } from "@/components/ui/badge"
import { statusLabel } from "@/lib/format"
import { cn } from "@/lib/utils"

const TONES: Record<string, string> = {
  processing: "bg-sky-100 text-sky-800",
  shipped: "bg-amber-100 text-amber-800",
  delivered: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-muted text-muted-foreground",
  return_requested: "bg-violet-100 text-violet-800",
}

export function OrderStatus({ status }: { status: string }) {
  return <Badge className={cn("border-0", TONES[status])}>{statusLabel(status)}</Badge>
}
