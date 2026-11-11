"use client"

import * as React from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"

import { Button } from "@/components/ui/button"
import { BRANDS, CATEGORIES, SORTS } from "@/lib/types"

/** The catalog's filter sidebar; every control writes the URL (the FILTER_PRODUCTS action does too). */
export function CatalogFilters() {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const [pending, start] = React.useTransition()

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value === null || value === "") next.delete(key)
    else next.set(key, value)
    start(() => router.push(`${pathname}${next.size ? `?${next}` : ""}`))
  }
  const active = [...params.keys()].filter((k) => k !== "sort_by").length

  return (
    <aside className="flex flex-col gap-6 text-sm" aria-label="Filters" aria-busy={pending} data-relay-ignore>
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Filters</h2>
        {active > 0 && (
          <Button variant="link" size="sm" className="h-auto px-0" onClick={() => start(() => router.push(pathname))}>
            Clear all
          </Button>
        )}
      </div>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1.5 font-medium">Category</legend>
        {[null, ...CATEGORIES].map((c) => (
          <label key={c ?? "all"} className="flex cursor-pointer items-center gap-2">
            <input
              type="radio"
              name="category"
              className="accent-[var(--primary)]"
              checked={(params.get("category") ?? null) === c}
              onChange={() => set("category", c)}
            />
            {c ?? "All categories"}
          </label>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1.5">
        <span className="font-medium">Brand</span>
        <select
          className="h-9 rounded-md border bg-background px-2"
          value={params.get("brand") ?? ""}
          onChange={(e) => set("brand", e.target.value)}
        >
          <option value="">Any brand</option>
          {BRANDS.map((b) => (
            <option key={b}>{b}</option>
          ))}
        </select>
      </label>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1.5 font-medium">Price (USD)</legend>
        <div className="flex items-center gap-2">
          <input
            key={`min-${params.get("min_price")}`}
            type="number"
            min={0}
            placeholder="Min"
            aria-label="Minimum price"
            defaultValue={params.get("min_price") ?? ""}
            onBlur={(e) => set("min_price", e.target.value)}
            className="h-9 w-full rounded-md border bg-background px-2"
          />
          <span className="text-muted-foreground">–</span>
          <input
            key={`max-${params.get("max_price")}`}
            type="number"
            min={0}
            placeholder="Max"
            aria-label="Maximum price"
            defaultValue={params.get("max_price") ?? ""}
            onBlur={(e) => set("max_price", e.target.value)}
            className="h-9 w-full rounded-md border bg-background px-2"
          />
        </div>
      </fieldset>
      <label className="flex flex-col gap-1.5">
        <span className="font-medium">Rating</span>
        <select
          className="h-9 rounded-md border bg-background px-2"
          value={params.get("min_rating") ?? ""}
          onChange={(e) => set("min_rating", e.target.value)}
        >
          <option value="">Any rating</option>
          <option value="4.5">4.5 stars & up</option>
          <option value="4">4 stars & up</option>
          <option value="3">3 stars & up</option>
        </select>
      </label>
      <div className="flex flex-col gap-2">
        <label className="flex cursor-pointer items-center gap-2">
          <input type="checkbox" className="accent-[var(--primary)]" checked={params.has("in_stock")} onChange={(e) => set("in_stock", e.target.checked ? "1" : null)} />
          In stock only
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input type="checkbox" className="accent-[var(--primary)]" checked={params.has("on_sale")} onChange={(e) => set("on_sale", e.target.checked ? "1" : null)} />
          On sale
        </label>
      </div>
    </aside>
  )
}

export function SortSelect() {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  return (
    <label className="flex items-center gap-2 text-sm" data-relay-ignore>
      <span className="text-muted-foreground">Sort</span>
      <select
        className="h-9 rounded-md border bg-background px-2"
        value={params.get("sort_by") ?? "featured"}
        onChange={(e) => {
          const next = new URLSearchParams(params)
          if (e.target.value === "featured") next.delete("sort_by")
          else next.set("sort_by", e.target.value)
          router.push(`${pathname}${next.size ? `?${next}` : ""}`)
        }}
      >
        {Object.entries(SORTS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </label>
  )
}
