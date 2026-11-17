import Link from "next/link"

import { AssistantToggle, ResetDemoButton } from "@/components/bank/header-controls"
import { SiteNav } from "@/components/bank/site-nav"

export function SiteHeader({ customerName, attention }: { customerName?: string; attention: number }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 lg:px-6">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold tracking-tight text-primary" aria-label="Kestrel Bank home">
          <svg viewBox="0 0 24 24" className="size-7" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
            <path d="M3 9.5 12 4l9 5.5" />
            <path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8" />
            <path d="M3 20h18" />
          </svg>
          <span className="hidden sm:inline">Kestrel Bank</span>
        </Link>
        <div className="ml-auto flex items-center gap-2">
          {customerName && <span className="hidden text-xs text-muted-foreground md:inline">Signed in as {customerName}</span>}
          <ResetDemoButton />
          <AssistantToggle />
        </div>
      </div>
      <SiteNav attention={attention} />
    </header>
  )
}
