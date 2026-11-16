import Link from "next/link"
import { ArrowRightIcon } from "lucide-react"

import { BookingStatus } from "@/components/bus/bits"
import { ScreenState } from "@/components/bus/screen-state"
import { bus } from "@/lib/bus"
import { dateTime, rupees, statusLabel } from "@/lib/format"
import { BOOKING_STATUSES, type BookingBrief } from "@/lib/types"
import { cn } from "@/lib/utils"

type Props = { searchParams: Promise<{ status?: string }> }

export default async function BookingsPage({ searchParams }: Props) {
  const { status } = await searchParams
  const valid = BOOKING_STATUSES.find((s) => s === status)
  const { bookings, total } = await bus<{ bookings: BookingBrief[]; total: number }>("/api/bookings", { query: { status: valid } })

  return (
    <div className="flex flex-col gap-6">
      <ScreenState
        name="bookings"
        value={{ status: valid ?? "all", shown: bookings.length, visible: bookings.slice(0, 20).map((b) => `${b.id} ${b.pnr} ${b.route} ${b.journey_date} ${b.status}`) }}
      />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">My trips</h1>
        <p className="text-sm text-muted-foreground">
          {total} booking{total === 1 ? "" : "s"}
        </p>
      </div>
      <nav className="flex flex-wrap gap-1.5" aria-label="Filter by status">
        {[undefined, ...BOOKING_STATUSES].map((s) => (
          <Link
            key={s ?? "all"}
            href={s ? `/bookings?status=${s}` : "/bookings"}
            aria-current={valid === s ? "page" : undefined}
            className={cn(
              "rounded-full border px-3 py-1 text-sm",
              valid === s ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
            )}
          >
            {s ? (s === "in_transit" ? "On the way" : statusLabel(s)) : "All"}
          </Link>
        ))}
      </nav>
      {bookings.length ? (
        <ul className="flex flex-col gap-3" data-testid="booking-list">
          {bookings.map((b) => (
            <li key={b.id}>
              <Link href={`/bookings/${b.id}`} className="group flex flex-wrap items-center gap-4 rounded-2xl border bg-card p-4 hover:border-primary sm:p-5">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 font-semibold">
                    {b.route} <BookingStatus status={b.status} />
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {dateTime(b.departs)} · {b.operator} · {b.bus_type}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    PNR {b.pnr} · {b.seats.length ? `seats ${b.seats.join(", ")}` : `${b.passengers} seat(s) cancelled`} · board at {b.boarding_point}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-semibold tabular-nums">{rupees(b.amount_paid)}</p>
                  {b.refunded > 0 && <p className="text-xs text-emerald-700">{rupees(b.refunded)} refunded</p>}
                  {b.can_rate && <p className="text-xs text-amber-700">Rate this trip</p>}
                </div>
                <ArrowRightIcon className="size-4 text-muted-foreground transition group-hover:translate-x-0.5" />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          No {valid ? statusLabel(valid).toLowerCase() : ""} trips. <Link href="/" className="text-primary underline">Search buses</Link>
        </div>
      )}
    </div>
  )
}
