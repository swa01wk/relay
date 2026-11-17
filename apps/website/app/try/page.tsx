import { ArrowRightIcon, MicIcon, TypeIcon } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"

import { Footer } from "@/components/footer"
import { Nav } from "@/components/nav"
import { ExampleShot } from "@/components/example-shot"
import { examples } from "@/lib/examples"

export const metadata: Metadata = {
  title: "Experience Center — Relay",
  description: "Talk to real apps running on Relay. Each visitor gets a private copy of the demo data.",
}

export default function TryPage() {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Experience Center</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance">Pick an app and start talking.</h1>
        <p className="mt-4 max-w-2xl text-muted">
          Every sandbox is yours alone: changes you make are private, can be reset at any time, and disappear after two
          hours. Voice needs microphone permission; text works everywhere.
        </p>
        <div className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {examples.map((e, i) => (
            <Link
              key={e.slug}
              href={`/try/${e.slug}`}
              className="group flex flex-col overflow-hidden rounded-xl border border-line-strong bg-raised transition-colors hover:border-accent/50"
            >
              <ExampleShot example={e} priority={i < 3} />
              <div className="flex flex-1 flex-col p-6">
                <div className="flex items-center gap-2">
                  <p className="font-mono text-xs text-faint">{e.industry}</p>
                  <span className="ml-auto flex gap-1.5 text-faint">
                    {e.modes.includes("voice") && <MicIcon className="size-4" aria-label="Voice" />}
                    {e.modes.includes("text") && <TypeIcon className="size-4" aria-label="Text" />}
                  </span>
                </div>
                <h2 className="mt-2 text-xl font-medium">{e.name}</h2>
                <p className="mt-2 text-sm text-muted">{e.description}</p>
                <ul className="mt-5 flex flex-wrap gap-2">
                  {e.highlights.map((h) => (
                    <li key={h} className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted">
                      {h}
                    </li>
                  ))}
                </ul>
                <span className="mt-auto inline-flex items-center gap-1.5 pt-6 text-sm text-accent">
                  Launch sandbox <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </main>
      <Footer />
    </>
  )
}
