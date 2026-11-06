import { ArrowLeftIcon, ExternalLinkIcon } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"

import { Logo } from "@/components/logo"
import { exampleBySlug, examples } from "@/lib/examples"

import { SandboxFrame } from "./sandbox-frame"

type Props = { params: Promise<{ slug: string }> }

export function generateStaticParams() {
  return examples.map((e) => ({ slug: e.slug }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const example = exampleBySlug((await params).slug)
  return example ? { title: `${example.name} sandbox — Relay`, description: example.tagline } : {}
}

export default async function SandboxPage({ params }: Props) {
  const example = exampleBySlug((await params).slug)
  if (!example) notFound()

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-4">
        <Link href="/try" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
          <ArrowLeftIcon className="size-4" />
          <span className="hidden sm:inline">Experience Center</span>
        </Link>
        <span className="text-line-strong">/</span>
        <Link href="/" aria-label="Relay home" className="hidden sm:block">
          <Logo className="text-sm" />
        </Link>
        <span className="truncate text-sm font-medium">{example.name}</span>
        <span className="hidden rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-faint md:inline">
          private sandbox · resets after 2 h
        </span>
        <a
          href={example.url}
          target="_blank"
          rel="noreferrer"
          className="ml-auto inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"
        >
          Full screen <ExternalLinkIcon className="size-4" />
        </a>
      </header>
      <SandboxFrame example={example} />
    </div>
  )
}
