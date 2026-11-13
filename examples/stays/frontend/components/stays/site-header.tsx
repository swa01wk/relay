import Link from "next/link"
import { HeartIcon, LuggageIcon, MessageSquareIcon } from "lucide-react"

import { AssistantToggle, ResetDemoButton } from "@/components/stays/header-controls"
import { Button } from "@/components/ui/button"

export function SiteHeader({ upcoming, guestName }: { upcoming: number; guestName?: string }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 lg:px-6">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold tracking-tight text-primary" aria-label="Roostly home">
          <svg viewBox="0 0 24 24" className="size-7" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
            <path d="M3 11.5 12 4l9 7.5" />
            <path d="M6 10v9h12v-9" />
            <path d="M10 19v-5h4v5" />
          </svg>
          <span className="hidden sm:inline">Roostly</span>
        </Link>
        <nav className="ml-auto flex items-center gap-1" aria-label="Account">
          <ResetDemoButton />
          <Button variant="ghost" size="sm" asChild>
            <Link href="/wishlists">
              <HeartIcon />
              <span className="hidden lg:inline">Wishlists</span>
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/trips" aria-label={`Trips (${upcoming} upcoming)`} data-testid="trips-link">
              <LuggageIcon />
              <span className="hidden lg:inline">Trips</span>
              {upcoming > 0 && (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-[11px] font-semibold text-primary-foreground tabular-nums">
                  {upcoming}
                </span>
              )}
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/inbox">
              <MessageSquareIcon />
              <span className="hidden lg:inline">Inbox</span>
            </Link>
          </Button>
          <AssistantToggle />
        </nav>
      </div>
      {guestName && (
        <div className="mx-auto hidden max-w-7xl justify-end px-4 pb-1.5 text-xs text-muted-foreground lg:flex lg:px-6">Signed in as {guestName}</div>
      )}
    </header>
  )
}
