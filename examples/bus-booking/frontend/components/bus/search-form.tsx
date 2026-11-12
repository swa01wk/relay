"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { ArrowLeftRightIcon, SearchIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { addDays, todayIst } from "@/lib/format"
import { CITIES } from "@/lib/types"

const field = "h-11 w-full rounded-lg border bg-background px-3 text-sm"

/**
 * From / To / Date. Ignored as a page form: the assistant searches with SEARCH_BUSES, which also
 * applies filters in one step.
 */
export function SearchForm({ from = "BLR", to = "HYD", date, compact = false }: { from?: string; to?: string; date?: string; compact?: boolean }) {
  const router = useRouter()
  const [src, setSrc] = React.useState(from)
  const [dst, setDst] = React.useState(to)
  const [day, setDay] = React.useState(date ?? todayIst())
  const today = todayIst()

  return (
    <form
      role="search"
      aria-label="Search buses"
      data-relay-ignore
      className={compact ? "flex flex-wrap items-end gap-2" : "grid gap-3 rounded-2xl border bg-card p-4 shadow-sm sm:grid-cols-[1fr_auto_1fr_1fr_auto] sm:items-end"}
      onSubmit={(e) => {
        e.preventDefault()
        if (src === dst) return
        router.push(`/search?from=${src}&to=${dst}&date=${day}`)
      }}
    >
      <label className="flex min-w-36 flex-1 flex-col gap-1 text-xs font-medium text-muted-foreground">
        From
        <select className={field} value={src} onChange={(e) => setSrc(e.target.value)}>
          {Object.entries(CITIES).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="size-11 self-end"
        aria-label="Swap cities"
        onClick={() => {
          setSrc(dst)
          setDst(src)
        }}
      >
        <ArrowLeftRightIcon />
      </Button>
      <label className="flex min-w-36 flex-1 flex-col gap-1 text-xs font-medium text-muted-foreground">
        To
        <select className={field} value={dst} onChange={(e) => setDst(e.target.value)}>
          {Object.entries(CITIES).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-w-36 flex-col gap-1 text-xs font-medium text-muted-foreground">
        Date of journey
        <input type="date" className={field} value={day} min={today} max={addDays(today, 60)} onChange={(e) => setDay(e.target.value)} />
      </label>
      <Button type="submit" size="lg" className="h-11" disabled={src === dst}>
        <SearchIcon />
        Search buses
      </Button>
      {src === dst && <p className="text-xs text-destructive sm:col-span-full">Pick two different cities.</p>}
    </form>
  )
}
