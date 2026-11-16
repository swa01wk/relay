"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { SearchIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { addDays, todayIst } from "@/lib/format"
import { DESTINATIONS, KINDS } from "@/lib/types"

const field = "h-10 w-full rounded-lg border bg-background px-3 text-sm"

export type SearchDefaults = { destination?: string; check_in?: string; check_out?: string; adults?: number; children?: number; pets?: number }

/** Where / when / who. Ignored as a page form: the assistant searches with SEARCH_STAYS in one step. */
export function SearchBar({ defaults = {}, compact = false }: { defaults?: SearchDefaults; compact?: boolean }) {
  const router = useRouter()
  const today = todayIst()
  const [where, setWhere] = React.useState(defaults.destination ?? "")
  const [checkIn, setCheckIn] = React.useState(defaults.check_in ?? "")
  const [checkOut, setCheckOut] = React.useState(defaults.check_out ?? "")
  const [adults, setAdults] = React.useState(defaults.adults ?? 2)
  const [children, setChildren] = React.useState(defaults.children ?? 0)
  const [pets, setPets] = React.useState(defaults.pets ?? 0)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const q = new URLSearchParams()
    if (where) q.set("destination", where)
    if (checkIn && checkOut && checkOut > checkIn) {
      q.set("check_in", checkIn)
      q.set("check_out", checkOut)
    }
    q.set("adults", String(adults))
    if (children) q.set("children", String(children))
    if (pets) q.set("pets", String(pets))
    router.push(`/search?${q}`)
  }

  return (
    <form
      role="search"
      aria-label="Search homes"
      data-relay-ignore
      onSubmit={submit}
      className={
        compact
          ? "flex flex-wrap items-end gap-2"
          : "grid gap-3 rounded-2xl border bg-card p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1.2fr_auto] lg:items-end"
      }
    >
      <label className="flex min-w-40 flex-1 flex-col gap-1 text-xs font-medium text-muted-foreground">
        Where
        <select className={field} value={where} onChange={(e) => setWhere(e.target.value)}>
          <option value="">Anywhere</option>
          <optgroup label="Destinations">
            {Object.entries(DESTINATIONS).map(([k, n]) => (
              <option key={k} value={n}>
                {n}
              </option>
            ))}
          </optgroup>
          <optgroup label="Kind of place">
            {Object.entries(KINDS).map(([k, n]) => (
              <option key={k} value={k}>
                {n}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
      <label className="flex min-w-36 flex-col gap-1 text-xs font-medium text-muted-foreground">
        Check-in
        <input
          type="date"
          className={field}
          value={checkIn}
          min={today}
          onChange={(e) => {
            setCheckIn(e.target.value)
            if (!checkOut || checkOut <= e.target.value) setCheckOut(addDays(e.target.value, 2))
          }}
        />
      </label>
      <label className="flex min-w-36 flex-col gap-1 text-xs font-medium text-muted-foreground">
        Check-out
        <input type="date" className={field} value={checkOut} min={checkIn ? addDays(checkIn, 1) : today} onChange={(e) => setCheckOut(e.target.value)} />
      </label>
      <fieldset className="flex gap-2">
        <legend className="sr-only">Guests</legend>
        {(
          [
            ["Adults", adults, setAdults, 1],
            ["Children", children, setChildren, 0],
            ["Pets", pets, setPets, 0],
          ] as const
        ).map(([label, value, set, min]) => (
          <label key={label} className="flex w-full min-w-16 flex-col gap-1 text-xs font-medium text-muted-foreground">
            {label}
            <input type="number" min={min} max={label === "Pets" ? 2 : 16} className={field} value={value} onChange={(e) => set(Math.max(min, Number(e.target.value) || 0))} />
          </label>
        ))}
      </fieldset>
      <Button type="submit" size="lg" className="h-10">
        <SearchIcon />
        Search
      </Button>
    </form>
  )
}
