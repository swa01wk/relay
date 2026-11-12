"use client"

import * as React from "react"
import { Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import { addTraveller, removeTraveller, type ActionResult } from "@/app/actions"
import { Button } from "@/components/ui/button"
import { GENDERS } from "@/lib/types"

const input = "h-9 w-full rounded-md border bg-background px-3 text-sm"

/** Save a co-traveller. A page form: "save my dad, Suresh, 61" fills it; the traveller saves. */
export function AddTravellerForm() {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(addTraveller, null)
  const formRef = React.useRef<HTMLFormElement>(null)
  React.useEffect(() => {
    if (state?.ok) {
      toast.success("Traveller saved")
      formRef.current?.reset()
    } else if (state?.error) toast.error(state.error)
  }, [state])
  return (
    <form ref={formRef} action={action} className="grid gap-3 rounded-2xl border bg-card p-5 sm:grid-cols-[1fr_90px_140px_auto] sm:items-end" data-relay-form="Add traveller" aria-label="Add traveller">
      <label className="flex flex-col gap-1 text-sm">
        Full name
        <input name="name" required maxLength={60} className={input} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Age
        <input name="age" type="number" min={1} max={110} required className={input} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Gender
        <select name="gender" required defaultValue="" className={input}>
          <option value="" disabled>
            Choose
          </option>
          {GENDERS.map((g) => (
            <option key={g} value={g}>
              {g[0].toUpperCase() + g.slice(1)}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" disabled={pending}>
        Save traveller
      </Button>
    </form>
  )
}

export function RemoveTravellerButton({ id, name }: { id: string; name: string }) {
  const [pending, start] = React.useTransition()
  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-8"
      aria-label={`Remove ${name}`}
      disabled={pending}
      onClick={() =>
        start(async () => {
          const res = await removeTraveller(id)
          if (!res.ok) toast.error(res.error)
        })
      }
    >
      <Trash2Icon />
    </Button>
  )
}
