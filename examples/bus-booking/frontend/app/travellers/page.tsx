import { ScreenState } from "@/components/bus/screen-state"
import { AddTravellerForm, RemoveTravellerButton } from "@/components/bus/traveller-forms"
import { bus } from "@/lib/bus"
import { rupees } from "@/lib/format"
import type { MyContext } from "@/lib/types"

export default async function TravellersPage() {
  const me = await bus<MyContext>("/api/me")
  return (
    <div className="flex flex-col gap-8">
      <ScreenState name="travellers" value={{ saved: me.saved_travellers.map((t) => `${t.id} ${t.name}`) }} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Travellers</h1>
        <p className="text-sm text-muted-foreground">Saved people fill the passenger details in one tap.</p>
      </div>
      <section className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border bg-card p-5 sm:col-span-2">
          <p className="text-xs text-muted-foreground">You</p>
          <p className="text-lg font-semibold">{me.traveller.name}</p>
          <p className="text-sm text-muted-foreground">
            {me.traveller.age} · {me.traveller.gender} · {me.traveller.home_city}
          </p>
          <p className="text-sm text-muted-foreground">
            {me.traveller.email} · {me.traveller.phone}
          </p>
        </div>
        <div className="rounded-2xl border bg-card p-5">
          <p className="text-xs text-muted-foreground">Wayline Wallet</p>
          <p className="text-2xl font-semibold tabular-nums">{rupees(me.wallet_balance)}</p>
          <p className="text-xs text-muted-foreground">{me.total_bookings} bookings · {rupees(me.lifetime_spend)} spent</p>
        </div>
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="font-semibold">Saved travellers</h2>
        {me.saved_travellers.length ? (
          <ul className="divide-y rounded-2xl border bg-card">
            {me.saved_travellers.map((t) => (
              <li key={t.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                <span className="flex-1 font-medium">{t.name}</span>
                <span className="text-muted-foreground">
                  {t.age} · {t.gender}
                </span>
                <RemoveTravellerButton id={t.id} name={t.name} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Nobody saved yet.</p>
        )}
        <AddTravellerForm />
      </section>
    </div>
  )
}
