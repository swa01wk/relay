"use client"

import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { formatUsd, monthLabel, type RevenuePoint } from "@/lib/crm"

const chartConfig = {
  revenue_usd: { label: "Revenue", color: "var(--chart-1)" },
  target_usd: { label: "Target", color: "var(--chart-3)" },
} satisfies ChartConfig

const RANGES = [
  { value: "12", label: "Last 12 months" },
  { value: "6", label: "Last 6 months" },
  { value: "3", label: "Last 3 months" },
]

export function ChartAreaInteractive({ revenue }: { revenue: RevenuePoint[] }) {
  const [range, setRange] = React.useState("12")
  const data = revenue.slice(-Number(range))
  const total = data.reduce((sum, point) => sum + point.revenue_usd, 0)
  const target = data.reduce((sum, point) => sum + point.target_usd, 0)

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>Revenue vs target</CardTitle>
        <CardDescription>
          {formatUsd(total, true)} closed-won against {formatUsd(target, true)} target (
          {Math.round((100 * total) / target)}%)
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            value={range}
            onValueChange={(value) => value && setRange(value)}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:px-4! @[767px]/card:flex"
          >
            {RANGES.map((r) => (
              <ToggleGroupItem key={r.value} value={r.value}>
                {r.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <Select value={range} onValueChange={setRange}>
            <SelectTrigger
              className="flex w-40 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden"
              size="sm"
              aria-label="Select a range"
            >
              <SelectValue placeholder="Last 12 months" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              {RANGES.map((r) => (
                <SelectItem key={r.value} value={r.value} className="rounded-lg">
                  {r.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="fillRevenue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-revenue_usd)" stopOpacity={0.9} />
                <stop offset="95%" stopColor="var(--color-revenue_usd)" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={monthLabel}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={(value: number) => formatUsd(value, true)}
            />
            <ChartTooltip
              cursor={false}
              content={
                <ChartTooltipContent
                  labelFormatter={(value) => monthLabel(String(value))}
                  formatter={(value, name) => (
                    <div className="flex w-full justify-between gap-4">
                      <span className="text-muted-foreground">
                        {chartConfig[name as keyof typeof chartConfig]?.label ?? name}
                      </span>
                      <span className="font-mono tabular-nums">{formatUsd(Number(value))}</span>
                    </div>
                  )}
                  indicator="dot"
                />
              }
            />
            <Area
              dataKey="revenue_usd"
              type="monotone"
              fill="url(#fillRevenue)"
              stroke="var(--color-revenue_usd)"
            />
            <Area
              dataKey="target_usd"
              type="step"
              fill="none"
              stroke="var(--color-target_usd)"
              strokeDasharray="4 4"
            />
            <ChartLegend content={<ChartLegendContent />} />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
