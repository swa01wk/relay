import Link from "next/link"

import { Logo } from "@/components/logo"

const links = [
  { href: "/#how", label: "How it works" },
  { href: "/#developers", label: "Developers" },
  { href: "/try", label: "Experience Center" },
  { href: "/#pricing", label: "Pricing" },
]

export function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur">
      <nav className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
        <Link href="/" aria-label="Relay home">
          <Logo />
        </Link>
        <ul className="hidden items-center gap-5 text-sm text-muted md:flex">
          {links.map((l) => (
            <li key={l.href}>
              <Link href={l.href} className="transition-colors hover:text-fg">
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/try"
            className="rounded-md border border-line-strong px-3 py-1.5 text-sm transition-colors hover:bg-raised md:hidden"
          >
            Try it
          </Link>
          <Link
            href="/#developers"
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
          >
            Get started
          </Link>
        </div>
      </nav>
    </header>
  )
}
