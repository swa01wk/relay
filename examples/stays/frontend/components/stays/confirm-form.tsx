"use client"

import * as React from "react"
import { Loader2Icon, LockIcon } from "lucide-react"

import { reserveStay, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { rupees } from "@/lib/format"
import type { MyContext } from "@/lib/types"

/**
 * Confirm and pay. Named like the reserve_stay tool's fields on purpose: the assistant fills this
 * page form from the chat ("tell the host we're arriving late") — only the guest presses the button.
 */
export function ConfirmForm({
  stay,
  total,
  instant,
  hostName,
  me,
}: {
  stay: { listing_id: string; check_in: string; check_out: string; adults: number; children: number; infants: number; pets: number }
  total: number
  instant: boolean
  hostName: string
  me: MyContext
}) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(reserveStay, null)
  const err = (name: string) => state?.fields?.[name]
  return (
    <form action={action} className="flex flex-col gap-8" data-relay-form="Confirm and pay" aria-label="Confirm and pay">
      {Object.entries(stay).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={String(v)} />
      ))}
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Message the host</h2>
        <p className="text-sm text-muted-foreground">
          {instant
            ? `Optional — say hello to ${hostName} or mention your arrival time.`
            : `${hostName} reviews each request. Say who's coming and what brings you here.`}
        </p>
        <textarea
          name="message_to_host"
          rows={4}
          maxLength={1000}
          required={!instant}
          aria-invalid={Boolean(err("message_to_host")) || undefined}
          placeholder={`Hi ${hostName}, we're…`}
          className="rounded-lg border bg-background px-3 py-2 text-sm aria-invalid:border-destructive"
        />
        {err("message_to_host") && <span className="text-xs text-destructive">{err("message_to_host")}</span>}
      </section>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-3 text-lg font-semibold">Pay with</legend>
        {me.payment_methods.map((m, i) => (
          <label key={m.id} className="flex cursor-pointer items-center gap-3 rounded-xl border bg-card p-4 text-sm has-checked:border-primary has-checked:ring-1 has-checked:ring-primary">
            <input type="radio" name="payment_method" value={m.id} defaultChecked={i === 0} className="accent-[var(--primary)]" />
            {m.label}
          </label>
        ))}
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <LockIcon className="size-3" /> Demo site: nothing is charged.
        </p>
      </fieldset>
      {state?.error && (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
          {state.error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={pending} data-testid="confirm-pay">
        {pending && <Loader2Icon className="animate-spin" />}
        {instant ? `Confirm and pay ${rupees(total)}` : "Request to book"}
      </Button>
      {!instant && <p className="-mt-6 text-center text-xs text-muted-foreground">You won&apos;t be charged unless {hostName} accepts.</p>}
    </form>
  )
}
