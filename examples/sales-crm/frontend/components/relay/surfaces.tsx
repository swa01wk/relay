"use client"

import * as React from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts"
import { ArrowUpDownIcon, CheckIcon, DownloadIcon, InfoIcon } from "lucide-react"
import {
  surfaceToCsv,
  type UiChartSurface,
  type UiComparisonSurface,
  type UiFormSurface,
  type UiSurface,
  type UiTableSurface,
} from "@sumukhj1219-wkt-org/relay-web-sdk"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { useRelay, type FormValues } from "@/components/relay/relay-provider"

const color = (index: number) => `var(--chart-${(index % 5) + 1})`

function cellText(value: unknown): string {
  if (value === null || value === undefined) return ""
  if (typeof value === "number") return value.toLocaleString("en-US")
  return typeof value === "object" ? JSON.stringify(value) : String(value)
}

function compareCells(a: unknown, b: unknown): number {
  const na = Number(a)
  const nb = Number(b)
  if (a !== "" && b !== "" && Number.isFinite(na) && Number.isFinite(nb)) return na - nb
  return cellText(a).localeCompare(cellText(b), undefined, { numeric: true })
}

function downloadCsv(surface: UiSurface, rows?: Array<Record<string, unknown>>) {
  const csv = surfaceToCsv(surface, rows)
  if (!csv) return
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }))
  const link = document.createElement("a")
  link.href = url
  link.download = `${(surface.title ?? surface.kind).replace(/[^\w-]+/g, "_").toLowerCase()}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function CsvButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} data-testid="surface-export-csv">
      <DownloadIcon />
      CSV
    </Button>
  )
}

function TableSurface({ surface }: { surface: UiTableSurface }) {
  const [query, setQuery] = React.useState("")
  const [sort, setSort] = React.useState<{ key: string; dir: 1 | -1 } | null>(null)
  const rows = React.useMemo(() => {
    const needle = query.trim().toLowerCase()
    const filtered = needle
      ? surface.rows.filter((row) =>
          surface.columns.some((col) => cellText(row[col.key]).toLowerCase().includes(needle)),
        )
      : surface.rows
    if (!sort) return filtered
    return [...filtered].sort((a, b) => compareCells(a[sort.key], b[sort.key]) * sort.dir)
  }, [surface, query, sort])
  const toggleSort = (key: string) =>
    setSort((prev) => (prev?.key !== key ? { key, dir: 1 } : prev.dir === 1 ? { key, dir: -1 } : null))

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter rows…"
          className="h-8"
        />
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {rows.length}/{surface.rows.length}
        </span>
        <CsvButton onClick={() => downloadCsv(surface, rows)} />
      </div>
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader className="bg-muted">
            <TableRow>
              {surface.columns.map((col) => (
                <TableHead key={col.key}>
                  <Button variant="ghost" size="sm" className="-ml-2 h-7" onClick={() => toggleSort(col.key)}>
                    {col.label}
                    <ArrowUpDownIcon />
                  </Button>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={index}>
                {surface.columns.map((col) => (
                  <TableCell key={col.key} className="tabular-nums">
                    {cellText(row[col.key])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {surface.caption && <p className="text-xs text-muted-foreground">{surface.caption}</p>}
    </div>
  )
}

function ChartSurface({ surface }: { surface: UiChartSurface }) {
  const { chartType, xKey, series, data, stacked } = surface
  if (!data.length || !series.length) {
    return <p className="text-sm text-muted-foreground">No numeric data to chart.</p>
  }
  if (chartType === "pie") {
    const valueKey = series[0].key
    const config = Object.fromEntries(
      data.map((point, i) => [String(point[xKey]), { label: String(point[xKey]), color: color(i) }]),
    ) satisfies ChartConfig
    return (
      <ChartContainer config={config} className="mx-auto aspect-square max-h-72" data-testid="surface-chart" data-chart-type="pie">
        <PieChart>
          <ChartTooltip content={<ChartTooltipContent nameKey={xKey} hideLabel />} />
          <Pie data={data} dataKey={valueKey} nameKey={xKey} innerRadius="45%">
            {data.map((_, i) => (
              <Cell key={i} fill={color(i)} />
            ))}
          </Pie>
          <ChartLegend content={<ChartLegendContent nameKey={xKey} />} className="flex-wrap" />
        </PieChart>
      </ChartContainer>
    )
  }

  const config = Object.fromEntries(
    series.map((s, i) => [s.key, { label: s.label, color: color(i) }]),
  ) satisfies ChartConfig
  const axes = (
    <>
      <CartesianGrid vertical={false} />
      <XAxis dataKey={xKey} tickLine={false} axisLine={false} tickMargin={8} minTickGap={16} />
      <YAxis tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => Intl.NumberFormat("en-US", { notation: "compact" }).format(v)} />
      <ChartTooltip content={<ChartTooltipContent />} />
      {series.length > 1 && <ChartLegend content={<ChartLegendContent />} />}
    </>
  )
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <CsvButton onClick={() => downloadCsv(surface)} />
      </div>
      <ChartContainer config={config} className="aspect-auto h-64 w-full" data-testid="surface-chart" data-chart-type={chartType}>
        {chartType === "line" ? (
          <LineChart data={data}>
            {axes}
            {series.map((s) => (
              <Line key={s.key} dataKey={s.key} type="monotone" stroke={`var(--color-${s.key})`} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        ) : chartType === "area" ? (
          <AreaChart data={data}>
            {axes}
            {series.map((s) => (
              <Area
                key={s.key}
                dataKey={s.key}
                type="monotone"
                stroke={`var(--color-${s.key})`}
                fill={`var(--color-${s.key})`}
                fillOpacity={0.25}
                stackId={stacked ? "a" : undefined}
              />
            ))}
          </AreaChart>
        ) : (
          <BarChart data={data}>
            {axes}
            {series.map((s) => (
              <Bar key={s.key} dataKey={s.key} fill={`var(--color-${s.key})`} radius={4} stackId={stacked ? "a" : undefined} />
            ))}
          </BarChart>
        )}
      </ChartContainer>
      {surface.caption && <p className="text-xs text-muted-foreground">{surface.caption}</p>}
    </div>
  )
}

function ComparisonSurface({ surface }: { surface: UiComparisonSurface }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          <Badge variant="secondary">differs</Badge> marks fields that are not the same
        </span>
        <CsvButton onClick={() => downloadCsv(surface)} />
      </div>
      <div className="overflow-hidden rounded-lg border">
        <Table data-testid="surface-comparison">
          <TableHeader className="bg-muted">
            <TableRow>
              <TableHead>Field</TableHead>
              {surface.entities.map((name) => (
                <TableHead key={name}>{name}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {surface.rows.map((row) => (
              <TableRow key={row.label} data-differs={row.differs}>
                <TableCell className="text-muted-foreground">
                  {row.label} {row.differs && <Badge variant="secondary">differs</Badge>}
                </TableCell>
                {row.values.map((value, i) => (
                  <TableCell key={i} className={row.differs ? "font-medium" : undefined}>
                    {value}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function initialValues(form: UiFormSurface): FormValues {
  return Object.fromEntries(
    form.fields.map((f) => [f.name, f.defaultValue ?? (f.type === "checkbox" ? false : "")]),
  )
}

function FormSurface({
  surface,
  onSubmit,
}: {
  surface: UiFormSurface
  onSubmit: (form: UiFormSurface, values: FormValues) => void
}) {
  const [values, setValues] = React.useState<FormValues>(() => initialValues(surface))
  const [sent, setSent] = React.useState(false)
  const status = useRelay().formStatus[surface.id]
  // Tool-bound forms can be retried after a failed save; other forms are one-shot.
  const submitted = surface.submitTool ? status?.state === "saving" || status?.state === "saved" : sent
  const set = (name: string, value: string | boolean) => setValues((prev) => ({ ...prev, [name]: value }))

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (submitted) return
    const out: FormValues = {}
    for (const field of surface.fields) {
      const value = values[field.name]
      out[field.name] = field.type === "number" ? (value === "" || value === null ? null : Number(value)) : value
    }
    onSubmit(surface, out)
    setSent(true)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" data-testid="surface-form" data-relay-ignore>
      {surface.description && <p className="text-sm text-muted-foreground">{surface.description}</p>}
      <fieldset disabled={submitted} className="grid gap-4 sm:grid-cols-2">
        {surface.fields.map((field) => {
          const id = `${surface.id}-${field.name}`
          const value = values[field.name]
          const label = (
            <Label htmlFor={id}>
              {field.label}
              {field.required && <span className="text-destructive">*</span>}
            </Label>
          )
          if (field.type === "checkbox") {
            return (
              <div key={field.name} className="flex items-center gap-2 sm:col-span-2">
                <Checkbox id={id} checked={Boolean(value)} onCheckedChange={(c) => set(field.name, c === true)} />
                {label}
              </div>
            )
          }
          return (
            <div key={field.name} className={`flex flex-col gap-2 ${field.type === "textarea" ? "sm:col-span-2" : ""}`}>
              {label}
              {field.type === "select" ? (
                <Select value={String(value ?? "")} onValueChange={(v) => set(field.name, v)} required={field.required}>
                  <SelectTrigger id={id} className="w-full">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {field.options?.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : field.type === "textarea" ? (
                <Textarea
                  id={id}
                  required={field.required}
                  placeholder={field.placeholder}
                  value={String(value ?? "")}
                  onChange={(e) => set(field.name, e.target.value)}
                />
              ) : (
                <Input
                  id={id}
                  type={field.type}
                  required={field.required}
                  placeholder={field.placeholder}
                  value={String(value ?? "")}
                  onChange={(e) => set(field.name, e.target.value)}
                />
              )}
            </div>
          )
        })}
      </fieldset>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={submitted}>
          {status?.state === "saving" ? "Saving…" : surface.submitLabel}
        </Button>
        {surface.submitTool ? (
          status?.state === "saved" ? (
            <Badge data-testid="form-saved">
              <CheckIcon />
              Saved
            </Badge>
          ) : status?.state === "failed" ? (
            <span className="text-sm text-destructive" data-testid="form-failed">
              Couldn&apos;t save{status.error ? ` (${status.error})` : ""} — fix and try again
            </span>
          ) : null
        ) : (
          sent && <Badge variant="secondary">Sent to the assistant (not saved)</Badge>
        )}
      </div>
    </form>
  )
}

function SurfaceBody({
  surface,
  onSubmitForm,
}: {
  surface: UiSurface
  onSubmitForm: (form: UiFormSurface, values: FormValues) => void
}) {
  switch (surface.kind) {
    case "table":
      return <TableSurface surface={surface} />
    case "chart":
      return <ChartSurface surface={surface} />
    case "comparison":
      return <ComparisonSurface surface={surface} />
    case "form":
      return <FormSurface key={surface.id} surface={surface} onSubmit={onSubmitForm} />
    case "markdown":
      // react-markdown does not render raw HTML, so model output cannot inject markup.
      return (
        <div className="prose-relay text-sm" data-testid="surface-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{surface.markdown}</ReactMarkdown>
        </div>
      )
    case "kv":
      return (
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          {surface.items.map((item, i) => (
            <React.Fragment key={`${item.label}-${i}`}>
              <dt className="text-muted-foreground">{item.label}</dt>
              <dd className="font-medium tabular-nums">{item.value}</dd>
            </React.Fragment>
          ))}
        </dl>
      )
    case "cards":
      return (
        <div className="grid gap-3 @xl/main:grid-cols-2">
          {surface.cards.map((card, i) => (
            <Card key={`${card.title}-${i}`} size="sm">
              <CardHeader>
                <CardTitle>{card.title}</CardTitle>
                {card.body && <CardDescription>{card.body}</CardDescription>}
              </CardHeader>
              {card.fields?.length ? (
                <CardContent className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                  {card.fields.map((field) => (
                    <React.Fragment key={field.label}>
                      <span className="text-muted-foreground">{field.label}</span>
                      <span className="tabular-nums">{field.value}</span>
                    </React.Fragment>
                  ))}
                </CardContent>
              ) : null}
            </Card>
          ))}
        </div>
      )
    case "notice":
      return (
        <Alert>
          <InfoIcon />
          {surface.title && <AlertTitle>{surface.title}</AlertTitle>}
          <AlertDescription>{surface.body}</AlertDescription>
        </Alert>
      )
  }
}

/** One agent-generated surface as a shadcn Card. */
export function SurfaceCard({
  surface,
  onSubmitForm,
}: {
  surface: UiSurface
  onSubmitForm: (form: UiFormSurface, values: FormValues) => void
}) {
  if (surface.kind === "notice") return <SurfaceBody surface={surface} onSubmitForm={onSubmitForm} />
  return (
    <Card data-testid="surface" data-kind={surface.kind}>
      <CardHeader>
        <CardTitle>{surface.title}</CardTitle>
        <CardAction>
          <Badge variant="outline" className="capitalize">
            {surface.kind === "kv" ? "details" : surface.kind}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        <SurfaceBody surface={surface} onSubmitForm={onSubmitForm} />
      </CardContent>
    </Card>
  )
}
