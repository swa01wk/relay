"use client"

import * as React from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AMENITIES, DEPARTURE_WINDOWS, OPERATORS, SORTS } from "@/lib/types"

const ROUTE_KEYS = new Set(["from", "to", "date"])

function useSetParam() {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const [pending, start] = React.useTransition()
  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value === null || value === "") next.delete(key)
    else next.set(key, value)
    start(() => router.push(`${pathname}?${next}`))
  }
  const clear = () => {
    const next = new URLSearchParams([...params].filter(([k]) => ROUTE_KEYS.has(k)))
    start(() => router.push(`${pathname}?${next}`))
  }
  return { params, set, clear, pending }
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded-lg border px-2.5 py-1.5 text-left text-xs transition",
        active ? "border-primary bg-primary/10 font-medium text-primary" : "hover:bg-muted",
      )}
    >
      {children}
    </button>
  )
}

/** The search page's filter sidebar; every control writes the URL (the SEARCH_BUSES action does too). */
export function SearchFilters() {
  const { params, set, clear, pending } = useSetParam()
  const active = [...params.keys()].filter((k) => !ROUTE_KEYS.has(k) && k !== "sort_by").length
  const toggle = (key: string, value: string) => set(key, params.get(key) === value ? null : value)

  return (
    <aside className="flex flex-col gap-6 text-sm" aria-label="Filters" aria-busy={pending} data-relay-ignore>
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Filters</h2>
        {active > 0 && (
          <Button variant="link" size="sm" className="h-auto px-0" onClick={clear}>
            Clear all
          </Button>
        )}
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 font-medium">Bus type</legend>
        <div className="grid grid-cols-2 gap-1.5">
          <Chip active={params.get("ac") === "1"} onClick={() => toggle("ac", "1")}>AC</Chip>
          <Chip active={params.get("ac") === "0"} onClick={() => toggle("ac", "0")}>Non-AC</Chip>
          <Chip active={params.get("sleeper") === "1"} onClick={() => toggle("sleeper", "1")}>Sleeper</Chip>
          <Chip active={params.get("sleeper") === "0"} onClick={() => toggle("sleeper", "0")}>Seater</Chip>
        </div>
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 font-medium">Departure time</legend>
        <div className="grid grid-cols-2 gap-1.5">
          {Object.entries(DEPARTURE_WINDOWS).map(([value, label]) => (
            <Chip key={value} active={params.get("departure_window") === value} onClick={() => toggle("departure_window", value)}>
              {label}
            </Chip>
          ))}
        </div>
      </fieldset>
      <label className="flex flex-col gap-1.5">
        <span className="font-medium">Operator</span>
        <select className="h-9 rounded-md border bg-background px-2" value={params.get("operator_id") ?? ""} onChange={(e) => set("operator_id", e.target.value)}>
          <option value="">Any operator</option>
          {Object.entries(OPERATORS).map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="font-medium">Max fare</span>
        <select className="h-9 rounded-md border bg-background px-2" value={params.get("max_fare") ?? ""} onChange={(e) => set("max_fare", e.target.value)}>
          <option value="">Any fare</option>
          {[500, 800, 1000, 1500, 2000].map((v) => (
            <option key={v} value={v}>
              Up to ₹{v.toLocaleString("en-IN")}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="font-medium">Rating</span>
        <select className="h-9 rounded-md border bg-background px-2" value={params.get("min_rating") ?? ""} onChange={(e) => set("min_rating", e.target.value)}>
          <option value="">Any rating</option>
          {[4.5, 4, 3.5].map((v) => (
            <option key={v} value={v}>
              {v}★ and up
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="font-medium">Amenity</span>
        <select className="h-9 rounded-md border bg-background px-2" value={params.get("amenity") ?? ""} onChange={(e) => set("amenity", e.target.value)}>
          <option value="">Any</option>
          {Object.entries(AMENITIES).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
    </aside>
  )
}

export function SortTabs() {
  const { params, set } = useSetParam()
  const current = params.get("sort_by") ?? "departure"
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Sort by" data-relay-ignore>
      {Object.entries(SORTS).map(([value, label]) => (
        <Chip key={value} active={current === value} onClick={() => set("sort_by", value === "departure" ? null : value)}>
          {label}
        </Chip>
      ))}
    </div>
  )
}
