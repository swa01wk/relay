"use client"

import { ShieldCheckIcon } from "lucide-react"

import { useRelay } from "@/components/relay/relay-provider"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

const label = (key: string) => key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())

/** Changes the assistant proposed (side-effecting tools): nothing is saved until Approve. */
export function ApprovalDialog() {
  const { approvals, approve, reject } = useRelay()
  const current = approvals[0]
  return (
    <Dialog
      open={Boolean(current)}
      onOpenChange={(open) => {
        if (!open && current) reject(current.approvalId)
      }}
    >
      {current && (
        <DialogContent data-testid="approval-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheckIcon className="size-5" />
              Approve this change?
            </DialogTitle>
            <DialogDescription>{current.summary}</DialogDescription>
          </DialogHeader>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 rounded-lg border p-3 text-sm">
            {Object.entries(current.arguments).map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="text-muted-foreground">{label(key)}</dt>
                <dd className="font-medium break-all">{String(value)}</dd>
              </div>
            ))}
          </dl>
          {approvals.length > 1 && (
            <p className="text-xs text-muted-foreground">{approvals.length - 1} more change(s) waiting</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => reject(current.approvalId)}>
              Reject
            </Button>
            <Button onClick={() => approve(current.approvalId)} data-testid="approval-approve">
              Approve &amp; save
            </Button>
          </DialogFooter>
        </DialogContent>
      )}
    </Dialog>
  )
}
