import Link from "next/link"

import { Logo } from "@/components/logo"

export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-10 text-sm text-muted sm:flex-row sm:items-center sm:px-6">
        <Logo className="text-fg" />
        <p className="sm:ml-4">Realtime voice and text assistants that drive your app. Preview.</p>
        <ul className="flex gap-5 sm:ml-auto">
          <li>
            <Link href="/try" className="hover:text-fg">
              Experience Center
            </Link>
          </li>
          <li>
            <a href="https://www.npmjs.com/package/@sumukhj1219-wkt-org/relay-web-sdk" className="hover:text-fg">
              Web SDK
            </a>
          </li>
          <li>
            <a href="https://www.npmjs.com/package/@sumukhj1219-wkt-org/relay-cli" className="hover:text-fg">
              CLI
            </a>
          </li>
        </ul>
      </div>
    </footer>
  )
}
