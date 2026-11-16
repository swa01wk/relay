"use client"

import { RotateCcwIcon, SparklesIcon } from "lucide-react"

import { SANDBOX, useRelay } from "@/components/relay/relay-provider"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"

export function SiteHeader({ title, asOf }: { title: string; asOf?: string }) {
  const { panelOpen, setPanelOpen, resetSandbox } = useRelay()
  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mx-2 data-[orientation=vertical]:h-4" />
        <h1 className="text-base font-medium">{title}</h1>
        {asOf && <span className="text-sm text-muted-foreground">as of {asOf}</span>}
        {SANDBOX && (
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            title="Your changes are private to you. Reset puts the demo data back."
            onClick={() => void resetSandbox()}
          >
            <RotateCcwIcon />
            Reset demo
          </Button>
        )}
        {!panelOpen && (
          <Button size="sm" className={SANDBOX ? "hidden lg:flex" : "ml-auto hidden lg:flex"} onClick={() => setPanelOpen(true)}>
            <SparklesIcon />
            Ask Relay
          </Button>
        )}
      </div>
    </header>
  )
}
