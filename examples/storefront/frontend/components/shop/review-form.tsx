"use client"

import * as React from "react"
import { toast } from "sonner"

import { writeReview, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"

/** "Write a review" — a page form the assistant can fill (registerPageForms); the shopper submits. */
export function ReviewForm({ productId }: { productId: string }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(writeReview.bind(null, productId), null)
  React.useEffect(() => {
    if (state?.ok) toast.success("Thanks — your review is live")
  }, [state])
  if (state?.ok) return null
  return (
    <form action={action} className="flex flex-col gap-3 rounded-xl border bg-card p-4" data-relay-form="Write a review" aria-label="Write a review">
      <h3 className="font-medium">Write a review</h3>
      <div className="grid gap-3 sm:grid-cols-[140px_1fr]">
        <label className="flex flex-col gap-1 text-sm">
          Rating
          <select name="rating" required defaultValue="5" className="h-9 rounded-md border bg-background px-2">
            {[5, 4, 3, 2, 1].map((n) => (
              <option key={n} value={n}>
                {n} star{n > 1 ? "s" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Headline
          <input name="title" required maxLength={120} placeholder="Sum it up" className="h-9 rounded-md border bg-background px-3" />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Review
        <textarea
          name="body"
          required
          minLength={10}
          maxLength={2000}
          rows={4}
          placeholder="What did you like or dislike?"
          className="rounded-md border bg-background px-3 py-2"
        />
      </label>
      {state?.error && <p className="text-sm text-destructive">{state.error}</p>}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Publishing…" : "Publish review"}
      </Button>
    </form>
  )
}
