"use client"

import * as React from "react"
import { toast } from "sonner"

import { createWishlist, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"

/** New wishlist. A page form: "make a list called Honeymoon" fills it; the guest creates it. */
export function CreateWishlistForm() {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(createWishlist, null)
  const ref = React.useRef<HTMLFormElement>(null)
  React.useEffect(() => {
    if (state?.ok) {
      toast.success("Wishlist created")
      ref.current?.reset()
    } else if (state?.error) toast.error(state.error)
  }, [state])
  return (
    <form ref={ref} action={action} className="flex max-w-md items-end gap-2" data-relay-form="New wishlist" aria-label="New wishlist">
      <label className="flex flex-1 flex-col gap-1 text-sm">
        New wishlist
        <input name="name" required maxLength={50} placeholder="Honeymoon ideas" className="h-9 rounded-md border bg-background px-3 text-sm" />
      </label>
      <Button type="submit" variant="outline" disabled={pending}>
        Create
      </Button>
    </form>
  )
}
