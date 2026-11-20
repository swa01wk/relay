import { inr } from "@/lib/format"
import type { AccountRow } from "@/lib/types"

export const RELATIONS = ["wife", "husband", "son", "daughter", "mother", "father", "brother", "sister"]

/** Savings / current accounts the customer can debit or credit. */
export function transactional(accounts: AccountRow[]): AccountRow[] {
  return accounts.filter((a) => /^(SB|CA)-/.test(a.id))
}

export function AccountSelect({ accounts, name = "from_account", defaultValue = "SB-01" }: { accounts: AccountRow[]; name?: string; defaultValue?: string }) {
  return (
    <select name={name} defaultValue={defaultValue} className="gv-input max-w-full">
      {transactional(accounts).map((a) => (
        <option key={a.id} value={a.id}>
          {a.number} — {a.type} ({a.id}) — ₹{inr(a.balance)}
        </option>
      ))}
    </select>
  )
}

export function RelationSelect({ name = "nominee_relation" }: { name?: string }) {
  return (
    <select name={name} className="gv-input" defaultValue="">
      <option value="">-- Select --</option>
      {RELATIONS.map((r) => (
        <option key={r} value={r}>
          {r[0].toUpperCase() + r.slice(1)}
        </option>
      ))}
    </select>
  )
}
