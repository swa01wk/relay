import { StarIcon } from "lucide-react"

import { cn } from "@/lib/utils"

export function Rating({ value, count, className }: { value: number; count?: number; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 text-sm", className)} aria-label={`${value} out of 5 stars`}>
      <span className="flex">
        {[1, 2, 3, 4, 5].map((n) => (
          <StarIcon
            key={n}
            className={cn("size-3.5", n <= Math.round(value) ? "fill-amber-400 text-amber-400" : "text-muted-foreground/40")}
          />
        ))}
      </span>
      <span className="font-medium">{value.toFixed(1)}</span>
      {count !== undefined && <span className="text-muted-foreground">({count})</span>}
    </span>
  )
}
