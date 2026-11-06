import { ArrowRightIcon, MicIcon, TypeIcon } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"

import { Footer } from "@/components/footer"
import { Nav } from "@/components/nav"
import { examples } from "@/lib/examples"

export const metadata: Metadata = {
  title: "Experience Center — Relay",
  description: "Talk to real apps running on Relay. Each visitor gets a private copy of the demo data.",
}

export default function TryPage() {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Experience Center</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance">Pick an app and start talking.</h1>
        <p className="mt-4 max-w-2xl text-muted">
          Every sandbox is yours alone: changes you make are private, can be reset at any time, and disappear after two
          hours. Voice needs microphone permission; text works everywhere.
        </p>
        <div className="mt-12 grid gap-4 md:grid-cols-2">
          {examples.map((e) => (
            <Link
              key={e.slug}
              href={`/try/${e.slug}`}
              className="group flex flex-col rounded-xl border border-line-strong bg-raised p-6 transition-colors hover:border-accent/50"
            >
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
              <span className="mt-6 inline-flex items-center gap-1.5 text-sm text-accent">
                Launch sandbox <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>
      </main>
      <Footer />
    </>
  )
}
