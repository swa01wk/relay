"use client"

import * as React from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { CATEGORIES } from "@/lib/types"
import { cn } from "@/lib/utils"

const select = "h-9 rounded-md border bg-background px-2 text-sm"

/** Statement filters; every control writes the URL (FILTER_TRANSACTIONS does too). */
export function TxnFilters({ accounts }: { accounts: { id: string; label: string }[] }) {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const [pending, start] = React.useTransition()
  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (!value) next.delete(key)
    else next.set(key, value)
    start(() => router.push(`${pathname}?${next}`))
  }
  const active = [...params.keys()].length > 0

  return (
    <section className={cn("flex flex-col gap-3 rounded-2xl border bg-card p-4", pending && "opacity-70")} aria-label="Filters" data-relay-ignore>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          set("query", String(new FormData(e.currentTarget).get("query") ?? "").trim())
        }}
      >
        {/* Uncontrolled; remounts when the URL's query changes (e.g. FILTER_TRANSACTIONS). */}
        <input key={params.get("query") ?? ""} name="query" defaultValue={params.get("query") ?? ""} placeholder="Search merchant, description or reference" className="h-9 flex-1 rounded-md border bg-background px-3 text-sm" aria-label="Search transactions" />
        <Button type="submit" variant="secondary" size="sm" className="h-9">
          Search
        </Button>
      </form>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <select className={select} value={params.get("account") ?? ""} onChange={(e) => set("account", e.target.value)} aria-label="Account">
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </select>
        <select className={select} value={params.get("category") ?? ""} onChange={(e) => set("category", e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {Object.entries(CATEGORIES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select className={select} value={params.get("direction") ?? ""} onChange={(e) => set("direction", e.target.value)} aria-label="Direction">
          <option value="">In and out</option>
          <option value="debit">Money out</option>
          <option value="credit">Money in</option>
        </select>
        <input type="date" className={select} value={params.get("from") ?? ""} onChange={(e) => set("from", e.target.value)} aria-label="From" />
        <input type="date" className={select} value={params.get("to") ?? ""} onChange={(e) => set("to", e.target.value)} aria-label="To" />
        <select className={select} value={params.get("sort") ?? "date"} onChange={(e) => set("sort", e.target.value === "date" ? "" : e.target.value)} aria-label="Sort">
          <option value="date">Newest first</option>
          <option value="amount">Largest first</option>
        </select>
      </div>
      {active && (
        <Button variant="ghost" size="sm" className="self-start" onClick={() => start(() => router.push(pathname))}>
          <XIcon /> Clear filters
        </Button>
      )}
    </section>
  )
}
