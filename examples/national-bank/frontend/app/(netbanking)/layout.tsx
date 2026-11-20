import Link from "next/link"

import { AssistantButton } from "@/components/vnb/assistant-button"
import { Logo } from "@/components/vnb/logo"
import { LeftMenu, SessionTimer, TopTabs } from "@/components/vnb/nb-nav"
import { Footer, Marquee } from "@/components/vnb/notices"
import { dmy } from "@/lib/format"
import { read } from "@/lib/vnb"
import type { MyContext } from "@/lib/types"

/** The signed-in internet banking shell: header, tab bar, notices, left menu tree, content. */
export default async function NetBankingLayout({ children }: { children: React.ReactNode }) {
  let me: MyContext | null = null
  try {
    me = await read<MyContext>("get_my_context")
  } catch {
    me = null
  }
  // The demo customer "last logged in" yesterday morning.
  const yesterday = me ? new Date(new Date(`${me.today}T00:00:00Z`).getTime() - 86400000).toISOString().slice(0, 10) : null
  const lastLogin = yesterday ? `${dmy(yesterday)} 09:47:12 AM` : "—"
  return (
    <div className="mx-auto max-w-[1400px] bg-white">
      <header className="flex flex-wrap items-center gap-3 border-b-4 border-[#e39b2d] px-3 py-2">
        <Link href="/home" className="!no-underline">
          <Logo size={38} />
        </Link>
        <div className="ml-auto flex flex-col items-end gap-0.5 text-[11px]">
          <span>
            Welcome, <b className="uppercase">{me?.customer.name ?? "Customer"}</b> | CIF: {me?.customer.cif ?? "—"} |{" "}
            <Link href="/">Logout</Link>
          </span>
          <span className="text-[#555]">
            Last login: {lastLogin} IST | <SessionTimer />
          </span>
          <AssistantButton compact />
        </div>
      </header>
      <TopTabs />
      <Marquee />
      <div className="grid gap-2 p-2 md:grid-cols-[220px_1fr]">
        <aside className="hidden md:block">
          <LeftMenu />
          <div className="mt-2 border border-[#d9b46a] bg-[#fff8e1] p-2 text-[10.5px]">
            <b className="text-[#a10000]">Security Tip:</b> Never share your OTP. Bank officials never ask for it. Log out after every session and clear the browser cache.
          </div>
        </aside>
        <div className="min-w-0">
          {me ? (
            children
          ) : (
            <div className="gv-msg-err">
              <b>Service temporarily unavailable.</b> The bank API (port 8096) isn&apos;t reachable. Start it:{" "}
              <code>docker compose -f infra/docker/docker-compose.yml up -d vnb-tools</code>, then reload.
            </div>
          )}
        </div>
      </div>
      <Footer />
    </div>
  )
}
