"use client"

import * as React from "react"
import { XIcon } from "lucide-react"

import { applyCoupon, removeCoupon, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"

export function CouponForm({ applied, note }: { applied: { code: string; description: string } | null; note: string | null }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(applyCoupon, null)
  const [removing, startRemove] = React.useTransition()
  if (applied) {
    return (
      <div className="flex flex-col gap-1 rounded-lg bg-accent px-3 py-2 text-sm text-accent-foreground">
        <div className="flex items-center gap-2">
          <span className="font-medium">{applied.code}</span>
          <span className="flex-1">{applied.description}</span>
          <Button variant="ghost" size="icon" className="size-7" aria-label="Remove coupon" disabled={removing} onClick={() => startRemove(async () => void (await removeCoupon()))}>
            <XIcon />
          </Button>
        </div>
        {note && <span className="text-xs text-amber-700">{note}</span>}
      </div>
    )
  }
  return (
    <form action={action} className="flex flex-col gap-1">
      <div className="flex gap-2">
        <input
          name="code"
          required
          placeholder="Coupon code"
          aria-label="Coupon code"
          className="h-9 flex-1 rounded-md border bg-background px-3 text-sm uppercase placeholder:normal-case"
        />
        <Button type="submit" variant="outline" disabled={pending}>
          Apply
        </Button>
      </div>
      {state?.error && <p className="text-xs text-destructive">{state.error}</p>}
      <p className="text-xs text-muted-foreground">Try WELCOME10, SAVE20 or FREESHIP.</p>
    </form>
  )
}
