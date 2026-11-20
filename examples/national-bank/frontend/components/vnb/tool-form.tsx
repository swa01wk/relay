"use client"

import * as React from "react"

import { submitTool, type ActionResult } from "@/app/actions"

/**
 * A portal form that runs one write tool. Its fields are named like that tool's parameters on purpose:
 * the assistant can fill the form on screen ("open an FD of 1 lakh for 444 days"), and only the customer
 * presses the button. `agree` adds the obligatory "I accept the terms" checkbox.
 */
export function ToolForm({
  tool,
  name,
  submitLabel = "Submit",
  agree,
  booleans = [],
  children,
  onResult,
  resetLabel = "Reset",
}: {
  tool: string
  name: string
  submitLabel?: string
  agree?: string
  booleans?: string[]
  children: React.ReactNode
  onResult?: (result: ActionResult) => void
  resetLabel?: string | null
}) {
  const formRef = React.useRef<HTMLFormElement>(null)
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(submitTool.bind(null, tool), null)
  React.useEffect(() => {
    if (state?.ok) formRef.current?.reset()
    if (state) onResult?.(state)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])

  return (
    <form ref={formRef} action={action} data-relay-form={name} aria-label={name}>
      {booleans.length > 0 && <input type="hidden" name="$booleans" value={booleans.join(",")} />}
      {agree && <input type="hidden" name="$needs_agree" value="1" />}
      <table className="gv-form">
        <tbody>{children}</tbody>
      </table>
      {agree && (
        <label className="mt-1.5 flex items-start gap-1.5">
          <input type="checkbox" name="agree" aria-invalid={Boolean(state?.fields?.agree) || undefined} />
          <span className="gv-note">{agree}</span>
        </label>
      )}
      {state?.ok && state.message && (
        <div className="gv-msg-ok" role="status">
          {state.message}
        </div>
      )}
      {state && !state.ok && (
        <div className="gv-msg-err" role="alert">
          {state.error}
          {state.fields && Object.keys(state.fields).length > 0 && (
            <span className="gv-note"> (Check: {Object.keys(state.fields).join(", ")})</span>
          )}
        </div>
      )}
      <div className="mt-1.5 flex gap-2">
        <button type="submit" className="gv-btn gv-btn-primary" disabled={pending}>
          {pending ? "Please wait…" : submitLabel}
        </button>
        {resetLabel && (
          <button type="reset" className="gv-btn">
            {resetLabel}
          </button>
        )}
      </div>
    </form>
  )
}

/** Field error marker for inputs inside a ToolForm (server errors come back by field name). */
export const inputProps = (name: string, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => ({ name, id: name, className: "gv-input", ...extra })
