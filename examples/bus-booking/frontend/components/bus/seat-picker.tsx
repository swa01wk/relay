"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { ArrowRightIcon } from "lucide-react"

import { useRelayAction, useScreenState } from "@/components/relay/relay-provider"
import { Button } from "@/components/ui/button"
import { rupees, time } from "@/lib/format"
import type { Point, Seat, TripDetail } from "@/lib/types"
import { cn } from "@/lib/utils"

const MAX_SEATS = 4
const DECK_LABEL = { lower: "Lower deck", upper: "Upper deck", main: "Seats" } as const

function SeatButton({ seat, selected, onToggle }: { seat: Seat; selected: boolean; onToggle: () => void }) {
  const taken = seat.status !== "available"
  const label = `${seat.id}, ${seat.deck === "main" ? "seat" : `${seat.deck} berth`}${seat.window ? ", window" : ""}, ${
    seat.status === "yours" ? "booked by you" : taken ? "booked" : `${rupees(seat.price)}${seat.women_only ? ", women only" : ""}`
  }`
  return (
    <button
      type="button"
      disabled={taken}
      aria-pressed={selected}
      aria-label={label}
      title={label}
      onClick={onToggle}
      data-seat={seat.id}
      className={cn(
        "flex flex-col items-center justify-center rounded-md border-2 text-[10px] leading-tight transition",
        seat.kind === "sleeper" ? "h-16 w-10" : "size-10",
        selected && "border-primary bg-primary text-primary-foreground",
        !selected && seat.status === "available" && (seat.women_only ? "seat-women hover:brightness-95" : "border-emerald-600/60 bg-background hover:bg-emerald-50"),
        seat.status === "booked" && "cursor-not-allowed border-transparent bg-muted-foreground/25 text-muted-foreground",
        seat.status === "booked_female" && "seat-booked-women cursor-not-allowed text-muted-foreground opacity-70",
        seat.status === "yours" && "cursor-not-allowed border-primary/40 bg-primary/15 text-primary",
      )}
    >
      <span className="font-semibold">{seat.id}</span>
      {seat.status === "available" && <span className="tabular-nums">₹{seat.price}</span>}
    </button>
  )
}

function Deck({ deck, seats, selected, toggle }: { deck: keyof typeof DECK_LABEL; seats: Seat[]; selected: string[]; toggle: (id: string) => void }) {
  const mine = seats.filter((s) => s.deck === deck)
  const cols = deck === "main" ? 5 : 4
  const rows = Math.max(...mine.map((s) => s.row)) + 1
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-muted-foreground">{DECK_LABEL[deck]}</p>
      <div
        className="grid w-fit gap-1.5 rounded-xl border bg-card p-3"
        style={{ gridTemplateColumns: `repeat(${cols}, auto)`, gridTemplateRows: `repeat(${rows}, auto)` }}
      >
        {mine.map((seat) => (
          <div key={seat.id} style={{ gridColumn: seat.col + 1, gridRow: seat.row + 1 }}>
            <SeatButton seat={seat} selected={selected.includes(seat.id)} onToggle={() => toggle(seat.id)} />
          </div>
        ))}
      </div>
    </div>
  )
}

function PointList({ name, title, points, value, onChange }: { name: string; title: string; points: Point[]; value: string; onChange: (id: string) => void }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-sm font-semibold">{title}</legend>
      {points.map((p) => (
        <label
          key={p.id}
          className="flex cursor-pointer items-start gap-3 rounded-lg border bg-card p-3 text-sm has-checked:border-primary has-checked:ring-1 has-checked:ring-primary"
        >
          <input type="radio" name={name} value={p.id} checked={value === p.id} onChange={() => onChange(p.id)} className="mt-1 accent-[var(--primary)]" />
          <span className="flex-1">
            <span className="font-medium">{p.name}</span>
            <span className="block text-xs text-muted-foreground">{p.landmark}</span>
          </span>
          <span className="font-medium tabular-nums">{time(p.time)}</span>
        </label>
      ))}
    </fieldset>
  )
}

/**
 * The seat map, boarding and dropping points and the running fare. The traveller clicks; the
 * assistant uses SELECT_SEATS. Neither books anything: Continue goes to the passenger details page.
 */
export function SeatPicker({ trip }: { trip: TripDetail }) {
  const router = useRouter()
  const [selected, setSelected] = React.useState<string[]>([])
  const [boarding, setBoarding] = React.useState(trip.boarding_points[0].id)
  const [dropping, setDropping] = React.useState(trip.dropping_points[trip.dropping_points.length - 1].id)
  const [notice, setNotice] = React.useState<string | null>(null)
  const byId = React.useMemo(() => new Map(trip.seats.map((s) => [s.id, s])), [trip.seats])
  const fare = selected.reduce((sum, id) => sum + (byId.get(id)?.price ?? 0), 0)
  const womenOnly = selected.filter((id) => byId.get(id)?.women_only)

  const toggle = (id: string) => {
    setNotice(null)
    setSelected((cur) => {
      if (cur.includes(id)) return cur.filter((s) => s !== id)
      if (cur.length >= MAX_SEATS) {
        setNotice(`At most ${MAX_SEATS} seats per booking.`)
        return cur
      }
      return [...cur, id]
    })
  }

  useScreenState("seat_selection", {
    trip_id: trip.trip_id,
    selected_seats: selected,
    boarding_point: boarding,
    dropping_point: dropping,
    fare_before_gst: fare,
    seats_available: trip.seats.filter((s) => s.status === "available").length,
  })

  useRelayAction(
    "SELECT_SEATS",
    (params) => {
      const raw = params.seats === undefined ? null : Array.isArray(params.seats) ? params.seats : String(params.seats).split(/[,\s]+/)
      const seats = raw ? raw.map((s) => String(s).trim().toUpperCase()).filter(Boolean) : selected
      if (seats.length > MAX_SEATS) throw new Error(`at most ${MAX_SEATS} seats`)
      const bad = seats.filter((s) => byId.get(s)?.status !== "available")
      if (bad.length) throw new Error(`not available: ${bad.join(", ")}`)
      const bp = params.boarding_point ? String(params.boarding_point).toUpperCase() : boarding
      const dp = params.dropping_point ? String(params.dropping_point).toUpperCase() : dropping
      if (!trip.boarding_points.some((p) => p.id === bp)) throw new Error(`boarding_point must be one of ${trip.boarding_points.map((p) => `${p.id} ${p.name}`).join(", ")}`)
      if (!trip.dropping_points.some((p) => p.id === dp)) throw new Error(`dropping_point must be one of ${trip.dropping_points.map((p) => `${p.id} ${p.name}`).join(", ")}`)
      setSelected(seats)
      setBoarding(bp)
      setDropping(dp)
      setNotice(null)
      const checkoutUrl = `/checkout?trip=${trip.trip_id}&seats=${seats.join(",")}&boarding=${bp}&dropping=${dp}`
      if (params.go_to_checkout) {
        if (!seats.length) throw new Error("select seats before going to checkout")
        router.push(checkoutUrl)
      }
      return {
        selected: seats,
        women_only: seats.filter((s) => byId.get(s)?.women_only),
        fare_before_gst: seats.reduce((sum, s) => sum + (byId.get(s)?.price ?? 0), 0),
        boarding_point: bp,
        dropping_point: dp,
        page: params.go_to_checkout ? "/checkout (Passenger details form)" : "seat map",
        next: params.go_to_checkout
          ? "Fill the Passenger details page form; only the traveller presses Pay."
          : "Call again with go_to_checkout: true (or the traveller presses Continue) to enter passenger details.",
      }
    },
    {
      description:
        "Select seats and boarding / dropping points on the open bus's seat map (replaces the current selection; omit a field to keep it), and optionally go on to the passenger details page. Only available seats; women_only seats only for women travellers. Does not book.",
      parameters: {
        type: "object",
        properties: {
          seats: { type: "array", items: { type: "string" }, description: "Seat ids like L4, U5 or S12 (max 4); [] clears" },
          boarding_point: { type: "string", description: `One of ${trip.boarding_points.map((p) => `${p.id} ${p.name}`).join(", ")}` },
          dropping_point: { type: "string", description: `One of ${trip.dropping_points.map((p) => `${p.id} ${p.name}`).join(", ")}` },
          go_to_checkout: { type: "boolean", description: "Then open the passenger details page with this selection" },
        },
      },
    },
  )

  const checkout = `/checkout?trip=${trip.trip_id}&seats=${selected.join(",")}&boarding=${boarding}&dropping=${dropping}`

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <section className="flex flex-col gap-4" aria-label="Seat map" data-testid="seat-map">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="size-3 rounded-sm border-2 border-emerald-600/60" /> Available</span>
          <span className="flex items-center gap-1.5"><span className="seat-women size-3 rounded-sm border-2" /> Women only</span>
          <span className="flex items-center gap-1.5"><span className="size-3 rounded-sm bg-muted-foreground/25" /> Booked</span>
          <span className="flex items-center gap-1.5"><span className="seat-booked-women size-3 rounded-sm border-2 opacity-70" /> Booked by a woman</span>
          <span className="flex items-center gap-1.5"><span className="size-3 rounded-sm bg-primary" /> Selected</span>
        </div>
        <div className="flex flex-wrap gap-6">
          {trip.decks.map((deck) => (
            <Deck key={deck} deck={deck} seats={trip.seats} selected={selected} toggle={toggle} />
          ))}
        </div>
        {trip.upper_berth_discount > 0 && <p className="text-xs text-muted-foreground">Upper berths are ₹{trip.upper_berth_discount} cheaper.</p>}
      </section>

      <aside className="flex flex-col gap-6">
        <PointList name="boarding" title="Boarding point" points={trip.boarding_points} value={boarding} onChange={setBoarding} />
        <PointList name="dropping" title="Dropping point" points={trip.dropping_points} value={dropping} onChange={setDropping} />
        <div className="sticky bottom-4 flex flex-col gap-3 rounded-2xl border bg-card p-4 shadow-sm" data-testid="selection-summary">
          <div className="flex items-baseline justify-between text-sm">
            <span>Seats</span>
            <span className="font-medium">{selected.length ? selected.join(", ") : "None yet"}</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-sm">Fare{trip.gst_pct ? ` (+${trip.gst_pct}% GST)` : ""}</span>
            <span className="text-xl font-semibold tabular-nums">{rupees(fare)}</span>
          </div>
          {womenOnly.length > 0 && <p className="text-xs text-pink-700">{womenOnly.join(", ")} can only be booked for a woman.</p>}
          {notice && <p className="text-xs text-destructive">{notice}</p>}
          <Button disabled={!selected.length} onClick={() => router.push(checkout)} data-testid="continue">
            Continue to passenger details <ArrowRightIcon />
          </Button>
        </div>
      </aside>
    </div>
  )
}
