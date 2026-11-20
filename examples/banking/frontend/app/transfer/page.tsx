import { CancelScheduledButton } from "@/components/bank/payee-forms"
import { ScreenState } from "@/components/bank/screen-state"
import { TransferForm } from "@/components/bank/transfer-form"
import { bank } from "@/lib/bank"
import { rupees, shortDate } from "@/lib/format"
import type { Account, Payee, Scheduled } from "@/lib/types"

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> }
const KEYS = ["to", "amount", "from_account", "mode", "note", "transfer_date", "repeat"] as const

export default async function TransferPage({ searchParams }: Props) {
  const sp = await searchParams
  const initial = Object.fromEntries(KEYS.flatMap((k) => (typeof sp[k] === "string" ? [[k, sp[k] as string]] : [])))
  const [{ payees }, { accounts }, { scheduled_transfers }, limits] = await Promise.all([
    bank<{ payees: Payee[] }>("/api/payees"),
    bank<{ accounts: Account[] }>("/api/accounts"),
    bank<{ scheduled_transfers: Scheduled[] }>("/api/scheduled"),
    bank<{ left_today: number; upi_left_today: number }>("/api/transfers/limits"),
  ])
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <ScreenState name="transfer" value={{ prefilled: initial }} />
      <section className="flex flex-col gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Send money</h1>
          <p className="text-sm text-muted-foreground">
            To a payee by UPI, IMPS or NEFT, or between your own accounts. {rupees(limits.left_today)} of today&apos;s transfer limit left (UPI{" "}
            {rupees(limits.upi_left_today)}).
          </p>
        </div>
        {/* A new prefill (START_TRANSFER) remounts the form with the new values. */}
        <TransferForm key={JSON.stringify(initial)} payees={payees} accounts={accounts.map((a) => ({ id: a.id, label: a.label, balance: a.balance }))} initial={initial} />
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Scheduled and repeating</h2>
        {scheduled_transfers.length === 0 ? (
          <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">Nothing scheduled.</p>
        ) : (
          <ul className="divide-y rounded-2xl border bg-card" data-testid="scheduled">
            {scheduled_transfers.map((s) => (
              <li key={s.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate font-medium">
                    {s.to_label}
                    {s.note ? ` · ${s.note}` : ""}
                  </span>
                  <span className="text-muted-foreground">
                    {rupees(s.amount)} · {s.repeat === "monthly" ? "every month, next" : "on"} {s.next_date ? shortDate(s.next_date) : "—"} · from {s.from_label}
                  </span>
                </div>
                <CancelScheduledButton id={s.id} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
