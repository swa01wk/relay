"use client";

import type { UiChartSurface } from "@sumukhj1219-wkt-org/relay-web-sdk";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const COLORS = [1, 2, 3, 4, 5, 6].map((n) => `hsl(var(--chart-${n}))`);
const color = (index: number) => COLORS[index % COLORS.length];

/** Renders any SDK-normalized chart spec — the model picks type, axis and series. */
export function PlaygroundChart({ surface }: { surface: UiChartSurface }) {
  const { chartType, xKey, series, data, yLabel, stacked } = surface;
  if (data.length === 0 || series.length === 0) {
    return <p className="text-sm text-muted-foreground">No numeric data to chart.</p>;
  }

  const axes = (
    <>
      <CartesianGrid strokeDasharray="3 3" vertical={false} />
      <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
      <YAxis
        tick={{ fontSize: 12 }}
        domain={["auto", "auto"]}
        label={
          yLabel
            ? { value: yLabel, angle: -90, position: "insideLeft", style: { fontSize: 12 } }
            : undefined
        }
      />
      <Tooltip />
      {series.length > 1 && <Legend />}
    </>
  );

  let chart: React.ReactElement;
  if (chartType === "pie") {
    const valueKey = series[0].key;
    chart = (
      <PieChart>
        <Pie data={data} dataKey={valueKey} nameKey={xKey} outerRadius="80%" label>
          {data.map((_, index) => (
            <Cell key={index} fill={color(index)} />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    );
  } else if (chartType === "line") {
    chart = (
      <LineChart data={data}>
        {axes}
        {series.map((s, i) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={color(i)} strokeWidth={2} dot />
        ))}
      </LineChart>
    );
  } else if (chartType === "area") {
    chart = (
      <AreaChart data={data}>
        {axes}
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={color(i)}
            fill={color(i)}
            fillOpacity={0.25}
            stackId={stacked ? "stack" : undefined}
          />
        ))}
      </AreaChart>
    );
  } else {
    chart = (
      <BarChart data={data}>
        {axes}
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            fill={color(i)}
            radius={[4, 4, 0, 0]}
            stackId={stacked ? "stack" : undefined}
          />
        ))}
      </BarChart>
    );
  }

  return (
    <div data-testid="playground-chart" data-chart-type={chartType}>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chart}
        </ResponsiveContainer>
      </div>
      {surface.caption && <p className="pt-1 text-xs text-muted-foreground">{surface.caption}</p>}
    </div>
  );
}
