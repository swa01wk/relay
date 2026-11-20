import type { Statement } from "@/lib/types"
import { read } from "@/lib/vnb"

const FIELDS = ["account_id", "from_date", "to_date", "last_n", "direction", "query", "min_amount", "max_amount"]
const cell = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`

/** The statement as a CSV file (opens in Excel), with the same filters as the page. */
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams
  const query: Record<string, string> = { limit: "200" }
  for (const key of FIELDS) {
    const value = params.get(key)
    if (value) query[key] = value
  }
  const statement = await read<Statement>("get_account_statement", query)
  const rows = [
    ["Txn Date", "Description", "Ref No.", "Debit", "Credit", "Balance"],
    ...[...statement.transactions].reverse().map((t) => [t.date, t.narration, t.ref, t.debit ?? "", t.credit ?? "", t.balance_after]),
  ]
  const csv = rows.map((r) => r.map(cell).join(",")).join("\r\n")
  const name = `statement-${query.account_id ?? "SB-01"}-${statement.to_date}.csv`
  return new Response(csv, { headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": `attachment; filename="${name}"` } })
}
