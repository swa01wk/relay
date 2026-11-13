"use client"

import * as React from "react"
import { ChevronDownIcon, ChevronRightIcon, SparklesIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useRelay } from "@/components/relay/relay-provider"
import { SurfaceBody } from "@/components/relay/surfaces"
import { cn } from "@/lib/utils"

const WIDE = new Set(["table", "comparison", "form", "markdown"])

/**
 * What the assistant shows (tables, charts, cards, forms), as a section of the page above the site
 * content — never an overlay. Hide collapses it to a one-line bar; new results show it again.
 */
export function ResultsCanvas() {
  const relay = useRelay()
  const { surfaces, canvasHidden, setCanvasHidden } = relay
  const [minimized, setMinimized] = React.useState<Record<string, boolean>>({})
  const ref = React.useRef<HTMLElement>(null)
  const count = surfaces.length

  React.useEffect(() => {
    if (count && !canvasHidden) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }, [surfaces, count, canvasHidden])

  if (!count) return null
  return (
    <section
      ref={ref}
      aria-label="Assistant results"
      className="border-b bg-muted/40"
      data-testid="results-canvas"
      data-relay-ignore // canvas forms are the assistant's own, not page forms
    >
      <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-2 lg:px-6">
        <SparklesIcon className="size-4 text-primary" />
        <h2 className="text-sm font-medium">Assistant results ({count})</h2>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={!canvasHidden}
            aria-controls="relay-canvas"
            aria-label={canvasHidden ? "Show results" : "Hide results"}
            onClick={() => setCanvasHidden(!canvasHidden)}
          >
            {canvasHidden ? `Show results (${count})` : "Hide"}
          </Button>
          {!canvasHidden && (
            <Button variant="ghost" size="sm" onClick={relay.clearSurfaces}>
              Clear
            </Button>
          )}
        </div>
      </div>
      {/* Hidden with the attribute, not unmounted, so half-filled forms keep their values. */}
      <div id="relay-canvas" hidden={canvasHidden} className="mx-auto max-w-7xl px-4 pb-4 lg:px-6">
        <div className="grid gap-4 lg:grid-cols-2">
          {surfaces.map((surface, index) => {
            const key = surface.id ?? String(index)
            const isMin = minimized[key] ?? false
            return (
              <article
                key={key}
                data-testid="surface"
                data-kind={surface.kind}
                className={cn("rounded-xl border bg-card shadow-xs", (WIDE.has(surface.kind) || count === 1) && "lg:col-span-2")}
              >
                <header className="flex items-center gap-2 px-4 py-2.5">
                  <h3 className="min-w-0 flex-1 truncate text-sm font-medium">{surface.title ?? surface.kind}</h3>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    aria-label={isMin ? "Expand" : "Minimize"}
                    aria-expanded={!isMin}
                    onClick={() => setMinimized((m) => ({ ...m, [key]: !isMin }))}
                  >
                    {isMin ? <ChevronRightIcon /> : <ChevronDownIcon />}
                  </Button>
                  <Button variant="ghost" size="icon" className="size-7" aria-label="Close" onClick={() => relay.removeSurface(index)}>
                    <XIcon />
                  </Button>
                </header>
                <div hidden={isMin} className="border-t px-4 py-4">
                  <SurfaceBody surface={surface} onSubmitForm={relay.submitForm} />
                </div>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}
