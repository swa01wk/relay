"use client"

import * as React from "react"
import { Loader2Icon, LockIcon } from "lucide-react"

import { placeOrder, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { money } from "@/lib/format"
import { COUNTRIES, type Address } from "@/lib/types"

const input = "h-10 w-full rounded-md border bg-background px-3 text-sm aria-invalid:border-destructive"

/**
 * Checkout. Native inputs on purpose: the assistant fills this page form from the chat
 * ("ship it to my office at …", registerPageForms) — and only the shopper presses Place order.
 */
export function CheckoutForm({
  address,
  email,
  shippingCosts,
  payments,
}: {
  address: Address
  email: string
  shippingCosts: { method: string; label: string; cost: number }[]
  payments: Record<string, string>
}) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(placeOrder, null)
  const err = (name: string) => state?.fields?.[name]
  const field = (name: keyof Address | "email", label: string, opts: { required?: boolean; defaultValue?: string; autoComplete?: string; span?: boolean } = {}) => (
    <label className={`flex flex-col gap-1.5 text-sm ${opts.span ? "sm:col-span-2" : ""}`}>
      <span>
        {label}
        {opts.required && <span className="text-destructive">*</span>}
      </span>
      <input
        name={name}
        required={opts.required}
        defaultValue={opts.defaultValue}
        autoComplete={opts.autoComplete}
        aria-invalid={Boolean(err(name)) || undefined}
        className={input}
        type={name === "email" ? "email" : "text"}
      />
      {err(name) && <span className="text-xs text-destructive">{err(name)}</span>}
    </label>
  )

  return (
    <form action={action} className="flex flex-col gap-8" data-relay-form="Checkout" aria-label="Checkout">
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Contact</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {field("email", "Email", { required: true, defaultValue: email, autoComplete: "email" })}
          {field("phone", "Phone (optional)", { defaultValue: address.phone, autoComplete: "tel" })}
        </div>
      </section>
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Shipping address</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {field("full_name", "Full name", { required: true, defaultValue: address.full_name, autoComplete: "name", span: true })}
          {field("address_line1", "Address", { required: true, defaultValue: address.address_line1, autoComplete: "address-line1", span: true })}
          {field("address_line2", "Apartment, suite (optional)", { defaultValue: address.address_line2, autoComplete: "address-line2", span: true })}
          {field("city", "City", { required: true, defaultValue: address.city, autoComplete: "address-level2" })}
          {field("state", "State / province", { required: true, defaultValue: address.state, autoComplete: "address-level1" })}
          {field("postal_code", "Postal code", { required: true, defaultValue: address.postal_code, autoComplete: "postal-code" })}
          <label className="flex flex-col gap-1.5 text-sm">
            <span>
              Country<span className="text-destructive">*</span>
            </span>
            <select name="country" required defaultValue={address.country} className={input}>
              {COUNTRIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
      </section>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-3 text-lg font-semibold">Shipping</legend>
        {shippingCosts.map((s, i) => (
          <label key={s.method} className="flex cursor-pointer items-center gap-3 rounded-xl border bg-card p-4 text-sm has-checked:border-primary has-checked:ring-1 has-checked:ring-primary">
            <input type="radio" name="shipping_method" value={s.method} defaultChecked={i === 0} className="accent-[var(--primary)]" />
            <span className="flex-1">{s.label}</span>
            <span className="font-medium tabular-nums">{s.cost === 0 ? "Free" : money(s.cost)}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-3 text-lg font-semibold">Payment</legend>
        {Object.entries(payments).map(([value, label], i) => (
          <label key={value} className="flex cursor-pointer items-center gap-3 rounded-xl border bg-card p-4 text-sm has-checked:border-primary has-checked:ring-1 has-checked:ring-primary">
            <input type="radio" name="payment_method" value={value} defaultChecked={i === 0} className="accent-[var(--primary)]" />
            {label}
          </label>
        ))}
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <LockIcon className="size-3" /> Demo store: nothing is charged.
        </p>
      </fieldset>
      <label className="flex flex-col gap-1.5 text-sm">
        Gift note (optional)
        <textarea name="gift_note" maxLength={300} rows={2} placeholder="Printed on the packing slip" className="rounded-md border bg-background px-3 py-2" />
      </label>
      {state?.error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{state.error}</p>}
      <Button type="submit" size="lg" disabled={pending} data-testid="place-order">
        {pending && <Loader2Icon className="animate-spin" />}
        Place order
      </Button>
    </form>
  )
}
