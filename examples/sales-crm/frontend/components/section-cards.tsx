import { TrendingDownIcon, TrendingUpIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { formatUsd, type Kpis } from "@/lib/crm"

function Trend({ pct }: { pct: number | null }) {
  if (pct === null) return null
  const Icon = pct >= 0 ? TrendingUpIcon : TrendingDownIcon
  return (
    <Badge variant="outline">
      <Icon />
      {pct >= 0 ? "+" : ""}
      {pct}%
    </Badge>
  )
}

export function SectionCards({ kpis }: { kpis: Kpis }) {
  const cards = [
    {
      label: "Revenue last month",
      value: formatUsd(kpis.last_month_revenue_usd),
      action: <Trend pct={kpis.last_month_change_pct} />,
      headline:
        kpis.last_month_change_pct === null
          ? "Closed-won revenue"
          : `${kpis.last_month_change_pct >= 0 ? "Up" : "Down"} vs the previous month`,
      detail: "Closed-won deals in the last full month",
    },
    {
      label: "Open pipeline",
      value: formatUsd(kpis.open_pipeline_usd, true),
      action: <Badge variant="outline">{kpis.open_deals} deals</Badge>,
      headline: `${formatUsd(kpis.weighted_pipeline_usd, true)} probability-weighted`,
      detail: "Prospecting through negotiation",
    },
    {
      label: "Win rate",
      value: `${kpis.win_rate_pct}%`,
      action: null,
      headline: "Won vs lost, last 12 months",
      detail: "Closed deals only",
    },
    {
      label: "Average won deal",
      value: formatUsd(kpis.avg_won_deal_usd),
      action: null,
      headline: "Mean closed-won amount",
      detail: "Last 12 months",
    },
  ]
  return (
    <div className="grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4 dark:*:data-[slot=card]:bg-card">
      {cards.map((card) => (
        <Card key={card.label} className="@container/card">
          <CardHeader>
            <CardDescription>{card.label}</CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
              {card.value}
            </CardTitle>
            {card.action && <CardAction>{card.action}</CardAction>}
          </CardHeader>
          <CardFooter className="flex-col items-start gap-1.5 text-sm">
            <div className="line-clamp-1 font-medium">{card.headline}</div>
            <div className="text-muted-foreground">{card.detail}</div>
          </CardFooter>
        </Card>
      ))}
    </div>
  )
}
