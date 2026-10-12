"use client"

import { SparklesIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useRelay } from "@/components/relay/relay-provider"
import { SurfaceCard } from "@/components/relay/surfaces"

/** Agent-generated surfaces, shown at the top of the dashboard. */
export function RelayInsights() {
  const { surfaces, clearSurfaces, submitForm } = useRelay()
  if (!surfaces.length) return null
  return (
    <section className="flex flex-col gap-3 px-4 lg:px-6" data-testid="relay-insights">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <SparklesIcon className="size-4" />
          Relay insights
        </h2>
        <Button variant="ghost" size="sm" onClick={clearSurfaces}>
          <XIcon />
          Clear
        </Button>
      </div>
      <div className="grid gap-4 @5xl/main:grid-cols-2">
        {surfaces.map((surface, index) => (
          <div
            key={surface.id ?? index}
            className={
              surface.kind === "table" || surface.kind === "comparison" || surface.kind === "form"
                ? "@5xl/main:col-span-2"
                : undefined
            }
          >
            <SurfaceCard surface={surface} onSubmitForm={submitForm} />
          </div>
        ))}
      </div>
    </section>
  )
}
