import Link from "next/link"
import {
  ArrowDownLeftIcon,
  ArrowUpRightIcon,
  BanknoteIcon,
  CarIcon,
  CreditCardIcon,
  FuelIcon,
  GraduationCapIcon,
  HeartPulseIcon,
  HomeIcon,
  LandmarkIcon,
  PlaneIcon,
  PopcornIcon,
  ReceiptIcon,
  RepeatIcon,
  ShoppingBagIcon,
  ShoppingCartIcon,
  UsersIcon,
  UtensilsIcon,
  type LucideIcon,
} from "lucide-react"

import { dateTime, rupees, shortDate, signed } from "@/lib/format"
import type { Txn } from "@/lib/types"
import { cn } from "@/lib/utils"

const ICONS: Partial<Record<Txn["category"], LucideIcon>> = {
  income: LandmarkIcon,
  rent: HomeIcon,
  groceries: ShoppingCartIcon,
  dining: UtensilsIcon,
  shopping: ShoppingBagIcon,
  transport: CarIcon,
  fuel: FuelIcon,
  utilities: ReceiptIcon,
  subscriptions: RepeatIcon,
  health: HeartPulseIcon,
  entertainment: PopcornIcon,
  travel: PlaneIcon,
  education: GraduationCapIcon,
  family: UsersIcon,
  investments: LandmarkIcon,
  cash: BanknoteIcon,
  card_payment: CreditCardIcon,
}

export function CategoryIcon({ category, className }: { category: Txn["category"]; className?: string }) {
  const Icon = ICONS[category] ?? (category === "interest" || category === "refunds" ? ArrowDownLeftIcon : ArrowUpRightIcon)
  return (
    <span className={cn("grid size-9 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground", className)}>
      <Icon className="size-4" />
    </span>
  )
}

/** A statement list: one row per transaction, linking to its page. */
export function TxnTable({ transactions, showAccount = true, showBalance = false }: { transactions: Txn[]; showAccount?: boolean; showBalance?: boolean }) {
  if (transactions.length === 0) return <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">No transactions match.</p>
  return (
    <ul className="divide-y rounded-2xl border bg-card" data-testid="transactions">
      {transactions.map((t) => (
        <li key={t.id}>
          <Link href={`/transactions/${t.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/50">
            <CategoryIcon category={t.category} />
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="flex items-center gap-2 truncate text-sm font-medium">
                {t.description}
                {t.possible_duplicate && <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">Possible duplicate</span>}
              </span>
              <span className="truncate text-xs text-muted-foreground" title={dateTime(t.posted_at)}>
                {shortDate(t.posted_at)} · {t.category_label}
                {showAccount && ` · ${t.account}`}
              </span>
            </div>
            <div className="flex flex-col items-end">
              <span className={cn("text-sm font-medium tabular-nums", t.direction === "credit" && "text-emerald-700")}>{signed(t.amount, t.direction)}</span>
              {showBalance && t.balance_after !== undefined && <span className="text-xs text-muted-foreground tabular-nums">Bal {rupees(t.balance_after)}</span>}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  )
}
