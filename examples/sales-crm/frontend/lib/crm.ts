/** CRM dashboard data from the sales CRM tools API (fetched server-side). */

export type Kpis = {
  open_pipeline_usd: number
  open_deals: number
  weighted_pipeline_usd: number
  win_rate_pct: number
  avg_won_deal_usd: number
  last_month_revenue_usd: number
  last_month_change_pct: number | null
}

export type RevenuePoint = { month: string; revenue_usd: number; target_usd: number }

export type PipelineStage = {
  stage: string
  deals: number
  amount_usd: number
  weighted_usd: number
}

export type Deal = {
  id: string
  name: string
  account_id: string
  account: string
  owner_id: string
  owner: string
  stage: string
  amount_usd: number
  probability: number
  created_date: string
  close_date: string
}

export type Dashboard = {
  as_of: string
  kpis: Kpis
  revenue: RevenuePoint[]
  pipeline: PipelineStage[]
  deals: Deal[]
}

const CRM_TOOLS_URL = process.env.CRM_TOOLS_URL ?? "http://localhost:8091"

/** `sandboxId`: the Experience Center visitor's own copy of the data (lib/sandbox.ts). */
export async function getDashboard(sandboxId?: string | null): Promise<Dashboard> {
  const res = await fetch(`${CRM_TOOLS_URL}/dashboard`, {
    cache: "no-store",
    headers: sandboxId ? { "X-Sandbox-Id": sandboxId } : {},
  })
  if (!res.ok) throw new Error(`CRM tools API returned ${res.status}`)
  return res.json() as Promise<Dashboard>
}

const compactUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
})
const fullUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
})

export const formatUsd = (value: number, compact = false) =>
  (compact ? compactUsd : fullUsd).format(value)

export const monthLabel = (month: string) =>
  new Date(`${month}-01T00:00:00`).toLocaleDateString("en-US", { month: "short", year: "2-digit" })
