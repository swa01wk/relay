import { AddPayeeForm, PayeeRowActions } from "@/components/bank/payee-forms"
import { bank } from "@/lib/bank"
import { dateTime, rupees, shortDate } from "@/lib/format"
import type { Payee } from "@/lib/types"

export default async function PayeesPage() {
  const { payees } = await bank<{ payees: Payee[] }>("/api/payees")
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section className="flex flex-col gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Payees</h1>
          <p className="text-sm text-muted-foreground">People and businesses you send money to.</p>
        </div>
        <ul className="divide-y rounded-2xl border bg-card" data-testid="payees">
          {payees.map((p) => (
            <li key={p.id} className="flex items-center gap-3 px-4 py-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-sm font-semibold text-accent-foreground">{p.name[0]}</span>
              <div className="flex min-w-0 flex-1 flex-col text-sm">
                <span className="truncate font-medium">
                  {p.name}
                  {p.nickname && <span className="font-normal text-muted-foreground"> · {p.nickname}</span>}
                </span>
                <span className="truncate text-muted-foreground">
                  {p.kind === "upi" ? `UPI ${p.upi_id}` : `${p.bank} ${p.account_masked} · ${p.ifsc}`}
                  {p.last_paid && ` · last paid ${rupees(p.last_paid.amount)} on ${shortDate(p.last_paid.date)}`}
                </span>
                {p.cooling_until && <span className="text-xs text-amber-700">New payee: up to ₹50,000 until {dateTime(p.cooling_until)}</span>}
              </div>
              <PayeeRowActions id={p.id} name={p.name} />
            </li>
          ))}
        </ul>
      </section>
      <AddPayeeForm />
    </div>
  )
}
