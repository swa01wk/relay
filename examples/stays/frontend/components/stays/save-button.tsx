"use client"

import * as React from "react"
import { HeartIcon } from "lucide-react"
import { toast } from "sonner"

import { toggleSaved } from "@/app/actions"
import { cn } from "@/lib/utils"

/** Heart on cards and the listing page: saves to the first wishlist, or removes from every list. */
export function SaveButton({ listingId, saved, className, withLabel = false }: { listingId: string; saved: boolean; className?: string; withLabel?: boolean }) {
  const [pending, start] = React.useTransition()
  const [optimistic, setOptimistic] = React.useOptimistic(saved)
  return (
    <button
      type="button"
      aria-pressed={optimistic}
      aria-label={optimistic ? "Remove from wishlists" : "Save to wishlist"}
      disabled={pending}
      onClick={(e) => {
        e.preventDefault()
        start(async () => {
          setOptimistic(!optimistic)
          const res = await toggleSaved(listingId, saved)
          if (!res.ok) toast.error(res.error)
          else toast.success(saved ? "Removed from your wishlists" : "Saved to your wishlist")
        })
      }}
      className={cn("inline-flex items-center gap-1.5 text-sm", className)}
    >
      <HeartIcon className={cn("size-5 drop-shadow", optimistic ? "fill-rose-500 text-rose-500" : "text-white")} />
      {withLabel && <span className="underline">{optimistic ? "Saved" : "Save"}</span>}
    </button>
  )
}
