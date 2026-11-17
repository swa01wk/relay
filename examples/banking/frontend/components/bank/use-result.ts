"use client"

import * as React from "react"
import { toast } from "sonner"

import type { ActionResult } from "@/app/actions"

/** Toast an action's outcome once per result. */
export function useResult(state: ActionResult | null, success: string, onOk?: () => void) {
  React.useEffect(() => {
    if (state?.ok) {
      toast.success(state.message ?? success)
      onOk?.()
    } else if (state?.error) toast.error(state.error)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])
}

export const inputClass = "h-9 w-full rounded-md border bg-background px-3 text-sm aria-invalid:border-destructive"
export const panelClass = "flex flex-col gap-3 rounded-2xl border bg-card p-5"
