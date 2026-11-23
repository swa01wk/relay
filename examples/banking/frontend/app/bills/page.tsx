import { BillCard } from "@/components/bank/bill-card"
import { ScreenState } from "@/components/bank/screen-state"
import { bank } from "@/lib/bank"
import { rupees } from "@/lib/format"
import type { Account, Biller } from "@/lib/types"

export default async function BillsPage() {
  const [{ billers, total_due }, { accounts }] = await Promise.all([
    bank<{ billers: Biller[]; total_due: number }>("/api/bills"),
    bank<{ accounts: Account[] }>("/api/accounts"),
  ])
  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="bills" value={{ total_due, due: billers.filter((b) => b.bill).map((b) => b.id) }} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Bills</h1>
        <p className="text-sm text-muted-foreground">{total_due > 0 ? `${rupees(total_due)} due across your billers.` : "Everything is paid."}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {billers.map((b) => (
          <BillCard key={b.id} biller={b} accounts={accounts.map((a) => ({ id: a.id, label: a.label }))} />
        ))}
      </div>
    </div>
  )
}
