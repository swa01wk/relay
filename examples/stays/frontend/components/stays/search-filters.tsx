"use client"

import * as React from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"

import { Button } from "@/components/ui/button"
import { AMENITIES, PROPERTY_TYPES, ROOM_TYPES, SORTS } from "@/lib/types"
import { cn } from "@/lib/utils"

const BASE_KEYS = new Set(["destination", "check_in", "check_out", "adults", "children", "infants", "pets"])
const FILTER_AMENITIES = ["pool", "wifi", "kitchen", "ac", "workspace", "parking", "fireplace", "hot_tub", "mountain_view", "lake_view", "beach_access", "breakfast"] as const

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn("rounded-full border px-3 py-1.5 text-xs transition", active ? "border-foreground bg-foreground text-background" : "hover:border-foreground/60")}
    >
      {children}
    </button>
  )
}

/** Filters under the search bar; every control writes the URL (the SEARCH_STAYS action does too). */
export function SearchFilters() {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const [pending, start] = React.useTransition()
  const go = (next: URLSearchParams) => start(() => router.push(`${pathname}?${next}`))
  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value === null || value === "") next.delete(key)
    else next.set(key, value)
    go(next)
  }
  const toggle = (key: string, value: string) => set(key, params.get(key) === value ? null : value)
  const amenities = params.getAll("amenities")
  const toggleAmenity = (a: string) => {
    const next = new URLSearchParams(params)
    next.delete("amenities")
    for (const x of amenities.includes(a) ? amenities.filter((y) => y !== a) : [...amenities, a]) next.append("amenities", x)
    go(next)
  }
  const active = [...new Set(params.keys())].filter((k) => !BASE_KEYS.has(k) && k !== "sort_by").length

  return (
    <section className="flex flex-col gap-3" aria-label="Filters" aria-busy={pending} data-relay-ignore>
      <div className="flex flex-wrap items-center gap-2">
        {Object.entries(PROPERTY_TYPES).map(([v, l]) => (
          <Chip key={v} active={params.get("property_type") === v} onClick={() => toggle("property_type", v)}>
            {l}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {FILTER_AMENITIES.map((a) => (
          <Chip key={a} active={amenities.includes(a)} onClick={() => toggleAmenity(a)}>
            {AMENITIES[a]}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Chip active={params.get("instant_book") === "1"} onClick={() => toggle("instant_book", "1")}>
          Instant book
        </Chip>
        <Chip active={params.get("superhost") === "1"} onClick={() => toggle("superhost", "1")}>
          Superhost
        </Chip>
        <select aria-label="Room type" className="h-8 rounded-full border bg-background px-3 text-xs" value={params.get("room_type") ?? ""} onChange={(e) => set("room_type", e.target.value)}>
          <option value="">Any type of place</option>
          {Object.entries(ROOM_TYPES).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select aria-label="Max price" className="h-8 rounded-full border bg-background px-3 text-xs" value={params.get("max_price") ?? ""} onChange={(e) => set("max_price", e.target.value)}>
          <option value="">Any price</option>
          {[3000, 5000, 7500, 10000, 15000].map((v) => (
            <option key={v} value={v}>
              Up to ₹{v.toLocaleString("en-IN")}/night
            </option>
          ))}
        </select>
        <select aria-label="Bedrooms" className="h-8 rounded-full border bg-background px-3 text-xs" value={params.get("min_bedrooms") ?? ""} onChange={(e) => set("min_bedrooms", e.target.value)}>
          <option value="">Any bedrooms</option>
          {[1, 2, 3, 4].map((v) => (
            <option key={v} value={v}>
              {v}+ bedrooms
            </option>
          ))}
        </select>
        <select aria-label="Rating" className="h-8 rounded-full border bg-background px-3 text-xs" value={params.get("min_rating") ?? ""} onChange={(e) => set("min_rating", e.target.value)}>
          <option value="">Any rating</option>
          {[4.8, 4.5, 4].map((v) => (
            <option key={v} value={v}>
              {v}★ and up
            </option>
          ))}
        </select>
        <select aria-label="Sort by" className="ml-auto h-8 rounded-full border bg-background px-3 text-xs" value={params.get("sort_by") ?? "recommended"} onChange={(e) => set("sort_by", e.target.value === "recommended" ? null : e.target.value)}>
          {Object.entries(SORTS).map(([v, l]) => (
            <option key={v} value={v}>
              Sort: {l}
            </option>
          ))}
        </select>
        {active > 0 && (
          <Button
            variant="link"
            size="sm"
            className="h-auto px-0"
            onClick={() => go(new URLSearchParams([...params].filter(([k]) => BASE_KEYS.has(k) || k === "sort_by")))}
          >
            Clear filters
          </Button>
        )}
      </div>
    </section>
  )
}
