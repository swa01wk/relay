"use client"

import { CheckIcon, CopyIcon } from "lucide-react"
import { useState } from "react"

export function CopyButton({ text, label = "Copy", className = "" }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      className={`inline-flex shrink-0 items-center justify-center rounded-md p-1.5 text-faint transition-colors hover:bg-raised hover:text-fg ${className}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          /* clipboard blocked; the text is still selectable */
        }
      }}
    >
      {copied ? <CheckIcon className="size-4 text-accent" /> : <CopyIcon className="size-4" />}
    </button>
  )
}
