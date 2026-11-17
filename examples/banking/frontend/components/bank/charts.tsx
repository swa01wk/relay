"use client"

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { compactRupees, monthLabel, rupees } from "@/lib/format"

const flowConfig = {
  income: { label: "Income", color: "var(--chart-2)" },
  spending: { label: "Spending", color: "var(--chart-1)" },
  invested: { label: "Invested", color: "var(--chart-3)" },
} satisfies ChartConfig

export function CashFlowChart({ months }: { months: { month: string; income: number; spending: number; invested: number }[] }) {
  return (
    <ChartContainer config={flowConfig} className="aspect-auto h-64 w-full">
      <BarChart data={months.map((m) => ({ ...m, label: monthLabel(m.month) }))} margin={{ left: 4, right: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} />
        <YAxis tickFormatter={compactRupees} tickLine={false} axisLine={false} width={48} />
        <ChartTooltip content={<ChartTooltipContent formatter={(v, name) => `${flowConfig[name as keyof typeof flowConfig]?.label ?? name}: ${rupees(Number(v))}`} />} />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar dataKey="income" fill="var(--color-income)" radius={4} />
        <Bar dataKey="spending" fill="var(--color-spending)" radius={4} />
        <Bar dataKey="invested" fill="var(--color-invested)" radius={4} />
      </BarChart>
    </ChartContainer>
  )
}

const catConfig = { amount: { label: "Spent", color: "var(--chart-1)" } } satisfies ChartConfig

export function CategoryChart({ rows }: { rows: { category: string; amount: number }[] }) {
  return (
    <ChartContainer config={catConfig} className="aspect-auto w-full" style={{ height: Math.max(160, rows.length * 34) }}>
      <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 16 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="category" tickLine={false} axisLine={false} width={120} />
        <ChartTooltip content={<ChartTooltipContent hideLabel formatter={(v, _n, item) => `${item.payload.category}: ${rupees(Number(v))}`} />} />
        <Bar dataKey="amount" fill="var(--color-amount)" radius={4} />
      </BarChart>
    </ChartContainer>
  )
}
