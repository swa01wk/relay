"use client"

import { ShieldCheckIcon } from "lucide-react"

import { useRelay } from "@/components/relay/relay-provider"
import { Button } from "@/components/ui/button"

const label = (key: string) => key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())

/** Changes the assistant proposed (side-effecting tools), shown in the assistant panel: nothing is saved until Approve. */
export function ApprovalCards() {
  const { approvals, approve, reject } = useRelay()
  return approvals.map((approval) => (
    <div
      key={approval.approvalId}
      data-testid="approval-dialog"
      role="group"
      aria-label="Approve this change?"
      className="flex flex-col gap-3 self-stretch rounded-lg border bg-background p-3 text-sm"
    >
      <div className="flex items-center gap-2 font-medium">
        <ShieldCheckIcon className="size-4" />
        Approve this change?
      </div>
      <p className="text-muted-foreground">{approval.summary}</p>
      {Object.keys(approval.arguments).length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-md border p-2 text-xs">
          {Object.entries(approval.arguments).map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{label(key)}</dt>
              <dd className="font-medium break-all">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="outline" onClick={() => reject(approval.approvalId)}>
          Reject
        </Button>
        <Button size="sm" onClick={() => approve(approval.approvalId)} data-testid="approval-approve">
          Approve &amp; save
        </Button>
      </div>
    </div>
  ))
}
