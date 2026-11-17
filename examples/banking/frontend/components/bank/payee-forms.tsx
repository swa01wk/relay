"use client"

import * as React from "react"
import Link from "next/link"
import { Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import { addPayee, cancelScheduled, removePayee, type ActionResult } from "@/app/actions"
import { inputClass, panelClass, useResult } from "@/components/bank/use-result"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/** Add a payee. Field names match the add_payee tool, so the assistant can fill it from the chat. */
export function AddPayeeForm() {
  const formRef = React.useRef<HTMLFormElement>(null)
  const [kind, setKind] = React.useState<"bank" | "upi">("bank")
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(addPayee, null)
  useResult(state, "Payee added", () => formRef.current?.reset())
  const err = (name: string) => state?.fields?.[name]
  return (
    <form ref={formRef} action={action} className={panelClass} data-relay-form="Add payee" aria-label="Add payee">
      <h2 className="font-semibold">Add a payee</h2>
      <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm" role="radiogroup" aria-label="Pay by">
        {(["bank", "upi"] as const).map((k) => (
          <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)} className={kind === k ? "flex-1 rounded-md bg-background py-1.5 font-medium shadow-sm" : "flex-1 py-1.5 text-muted-foreground"}>
            {k === "bank" ? "Bank account" : "UPI ID"}
          </button>
        ))}
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Name as on their account
        <input name="name" required minLength={2} maxLength={80} aria-invalid={Boolean(err("name")) || undefined} className={inputClass} />
      </label>
      {kind === "bank" ? (
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-sm">
            Account number
            <input name="account_number" inputMode="numeric" aria-invalid={Boolean(err("account_number")) || undefined} className={inputClass} />
            {err("account_number") && <span className="text-xs text-destructive">{err("account_number")}</span>}
          </label>
          <label className="flex flex-col gap-1 text-sm">
            IFSC
            <input name="ifsc" maxLength={11} className={cn(inputClass, "uppercase")} aria-invalid={Boolean(err("ifsc")) || undefined} />
            {err("ifsc") && <span className="text-xs text-destructive">{err("ifsc")}</span>}
          </label>
        </div>
      ) : (
        <label className="flex flex-col gap-1 text-sm">
          UPI ID
          <input name="upi_id" placeholder="name@okicici" aria-invalid={Boolean(err("upi_id")) || undefined} className={inputClass} />
        </label>
      )}
      <label className="flex flex-col gap-1 text-sm">
        Nickname (optional)
        <input name="nickname" maxLength={30} className={inputClass} />
      </label>
      <p className="text-xs text-muted-foreground">For the first 24 hours you can send a new payee up to ₹50,000 in total.</p>
      <Button type="submit" disabled={pending} className="self-start">
        Add payee
      </Button>
    </form>
  )
}

export function PayeeRowActions({ id, name }: { id: string; name: string }) {
  const [pending, start] = React.useTransition()
  return (
    <div className="flex gap-1">
      <Button variant="outline" size="sm" asChild>
        <Link href={`/transfer?to=${id}`}>Pay</Link>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        aria-label={`Remove ${name}`}
        disabled={pending}
        onClick={() => {
          if (!window.confirm(`Remove ${name}? Scheduled transfers to them are cancelled too.`)) return
          start(async () => {
            const res = await removePayee(id)
            if (res.ok) toast.success(res.message ?? "Payee removed")
            else toast.error(res.error)
          })
        }}
      >
        <Trash2Icon />
      </Button>
    </div>
  )
}

export function CancelScheduledButton({ id }: { id: string }) {
  const [pending, start] = React.useTransition()
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={pending}
      onClick={() =>
        start(async () => {
          const res = await cancelScheduled(id)
          if (res.ok) toast.success(res.message ?? "Cancelled")
          else toast.error(res.error)
        })
      }
    >
      Cancel
    </Button>
  )
}

