"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  ArrowLeftRightIcon,
  ChartPieIcon,
  CreditCardIcon,
  LandmarkIcon,
  ListIcon,
  PiggyBankIcon,
  ReceiptIcon,
  UsersIcon,
} from "lucide-react"

import { cn } from "@/lib/utils"

const LINKS = [
  { href: "/", label: "Accounts", icon: LandmarkIcon },
  { href: "/transactions", label: "Transactions", icon: ListIcon },
  { href: "/transfer", label: "Transfer", icon: ArrowLeftRightIcon },
  { href: "/payees", label: "Payees", icon: UsersIcon },
  { href: "/bills", label: "Bills", icon: ReceiptIcon },
  { href: "/cards", label: "Cards", icon: CreditCardIcon },
  { href: "/deposits", label: "Deposits", icon: PiggyBankIcon },
  { href: "/insights", label: "Insights", icon: ChartPieIcon },
]

export function SiteNav({ attention }: { attention: number }) {
  const pathname = usePathname()
  return (
    <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-2 lg:px-4" aria-label="Main">
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" || pathname.startsWith("/accounts") : pathname.startsWith(href)
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition",
              active ? "border-primary font-medium text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-4" />
            {label}
            {href === "/" && attention > 0 && (
              <span className="grid h-4 min-w-4 place-items-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white tabular-nums">{attention}</span>
            )}
          </Link>
        )
      })}
    </nav>
  )
}
