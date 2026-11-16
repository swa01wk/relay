import Link from "next/link"
import { BadgePercentIcon, TicketIcon, UsersIcon } from "lucide-react"

import { AssistantToggle, ResetDemoButton } from "@/components/bus/header-controls"
import { Button } from "@/components/ui/button"

export function SiteHeader({ upcoming, travellerName }: { upcoming: number; travellerName?: string }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 lg:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight" aria-label="Wayline home">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 17c3-8 5-10 8-10s5 2 8 10" />
              <circle cx="12" cy="7" r="1.6" fill="currentColor" stroke="none" />
            </svg>
          </span>
          <span className="hidden sm:inline">Wayline</span>
        </Link>
        <nav className="ml-auto flex items-center gap-1" aria-label="Account">
          <ResetDemoButton />
          <Button variant="ghost" size="sm" asChild>
            <Link href="/offers">
              <BadgePercentIcon />
              <span className="hidden lg:inline">Offers</span>
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/travellers">
              <UsersIcon />
              <span className="hidden lg:inline">Travellers</span>
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/bookings" aria-label={`My trips (${upcoming} upcoming)`} data-testid="trips-link">
              <TicketIcon />
              <span className="hidden lg:inline">My trips</span>
              {upcoming > 0 && (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-[11px] font-semibold text-primary-foreground tabular-nums">
                  {upcoming}
                </span>
              )}
            </Link>
          </Button>
          <AssistantToggle />
        </nav>
      </div>
      {travellerName && (
        <div className="mx-auto hidden max-w-7xl justify-end px-4 pb-1.5 text-xs text-muted-foreground lg:flex lg:px-6">Signed in as {travellerName}</div>
      )}
    </header>
  )
}
