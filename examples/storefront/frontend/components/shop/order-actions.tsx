"use client"

import * as React from "react"
import { RotateCwIcon } from "lucide-react"
import { toast } from "sonner"

import { cancelOrder, reorder, requestReturn, updateOrderAddress, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { CANCEL_REASONS, COUNTRIES, RETURN_REASONS, type Address } from "@/lib/types"

const input = "h-9 w-full rounded-md border bg-background px-3 text-sm"

function useResult(state: ActionResult | null, success: string) {
  React.useEffect(() => {
    if (state?.ok) toast.success(success)
    else if (state?.error) toast.error(state.error)
  }, [state, success])
}

/** Cancel (status processing). A page form: the assistant can pick the reason; the shopper confirms. */
export function CancelOrderForm({ orderId }: { orderId: string }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(cancelOrder.bind(null, orderId), null)
  useResult(state, "Order cancelled — your refund is on its way")
  return (
    <form action={action} className="flex flex-col gap-3 rounded-2xl border bg-card p-5" data-relay-form="Cancel order" aria-label="Cancel order">
      <h3 className="font-medium">Cancel this order</h3>
      <label className="flex flex-col gap-1 text-sm">
        Reason
        <select name="reason" className={input} defaultValue="changed_my_mind">
          {Object.entries(CANCEL_REASONS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" variant="destructive" disabled={pending} className="self-start">
        Cancel order
      </Button>
    </form>
  )
}

export function ReturnForm({ orderId, until }: { orderId: string; until: string | null }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(requestReturn.bind(null, orderId), null)
  useResult(state, "Return started — your label is ready")
  return (
    <form action={action} className="flex flex-col gap-3 rounded-2xl border bg-card p-5" data-relay-form="Return items" aria-label="Return items">
      <h3 className="font-medium">Return this order</h3>
      {until && <p className="text-xs text-muted-foreground">Free returns until {until}.</p>}
      <label className="flex flex-col gap-1 text-sm">
        Reason
        <select name="reason" required className={input} defaultValue="">
          <option value="" disabled>
            Choose a reason
          </option>
          {Object.entries(RETURN_REASONS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Notes (optional)
        <textarea name="notes" maxLength={500} rows={3} className="rounded-md border bg-background px-3 py-2" placeholder="What went wrong?" />
      </label>
      <Button type="submit" disabled={pending} className="self-start">
        Start return
      </Button>
    </form>
  )
}

export function AddressForm({ orderId, address }: { orderId: string; address: Address }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(updateOrderAddress.bind(null, orderId), null)
  useResult(state, "Shipping address updated")
  const f = (name: keyof Address, label: string, required = true) => (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <input name={name} required={required} defaultValue={address[name]} className={input} />
    </label>
  )
  return (
    <form action={action} className="flex flex-col gap-3 rounded-2xl border bg-card p-5" data-relay-form="Change shipping address" aria-label="Change shipping address">
      <h3 className="font-medium">Change shipping address</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {f("full_name", "Full name")}
        {f("address_line1", "Address")}
        {f("address_line2", "Apartment, suite", false)}
        {f("city", "City")}
        {f("state", "State / province")}
        {f("postal_code", "Postal code")}
        <label className="flex flex-col gap-1 text-sm">
          Country
          <select name="country" defaultValue={address.country} className={input}>
            {COUNTRIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        {f("phone", "Phone", false)}
      </div>
      <Button type="submit" variant="outline" disabled={pending} className="self-start">
        Save address
      </Button>
    </form>
  )
}

export function ReorderButton({ orderId }: { orderId: string }) {
  const [pending, start] = React.useTransition()
  return (
    <Button
      variant="outline"
      disabled={pending}
      onClick={() =>
        start(async () => {
          const result = await reorder(orderId)
          if (result && !result.ok) toast.error(result.error ?? "Couldn't add the items")
        })
      }
    >
      <RotateCwIcon /> Buy again
    </Button>
  )
}
