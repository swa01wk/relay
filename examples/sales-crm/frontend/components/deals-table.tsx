"use client"

import * as React from "react"
import {
  createColumnHelper,
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  tableFeatures,
  useTable,
} from "@tanstack/react-table"
import { ArrowUpDownIcon, ChevronLeftIcon, ChevronRightIcon, XIcon } from "lucide-react"

import { useRelay, useRelayAction } from "@/components/relay/relay-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatUsd, type Deal } from "@/lib/crm"
import { cn } from "@/lib/utils"

const STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
const OPEN = new Set(STAGES.slice(0, 4))

const VIEWS = {
  open: (d: Deal) => OPEN.has(d.stage),
  won: (d: Deal) => d.stage === "Closed Won",
  lost: (d: Deal) => d.stage === "Closed Lost",
  all: () => true,
} as const
type View = keyof typeof VIEWS

export type DealFilters = {
  view: View
  search: string
  minAmount: number | null
  maxAmount: number | null
  stage: string | null
  owner: string | null
}

const DEFAULT_FILTERS: DealFilters = {
  view: "open",
  search: "",
  minAmount: null,
  maxAmount: null,
  stage: null,
  owner: null,
}

/** The single source of truth for what the table shows (UI controls and the agent both use it). */
export function filterDeals(deals: Deal[], f: DealFilters): Deal[] {
  const needle = f.search.trim().toLowerCase()
  return deals.filter(
    (d) =>
      VIEWS[f.view](d) &&
      (f.minAmount === null || d.amount_usd >= f.minAmount) &&
      (f.maxAmount === null || d.amount_usd <= f.maxAmount) &&
      (!f.stage || d.stage.toLowerCase() === f.stage.toLowerCase()) &&
      (!f.owner || d.owner.toLowerCase().includes(f.owner.toLowerCase())) &&
      (!needle || [d.account, d.name, d.owner, d.id].join(" ").toLowerCase().includes(needle)),
  )
}

const num = (v: unknown) => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v))
const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : null)

/** Apply agent params to filters. Stage filters imply the matching view so they are visible. */
function filtersFromParams(current: DealFilters, p: Record<string, unknown>): DealFilters {
  const base = p.reset === true ? DEFAULT_FILTERS : current
  const next: DealFilters = { ...base }
  if ("view" in p && typeof p.view === "string" && p.view in VIEWS) next.view = p.view as View
  if ("search" in p) next.search = str(p.search) ?? ""
  if ("min_amount" in p) next.minAmount = num(p.min_amount)
  if ("max_amount" in p) next.maxAmount = num(p.max_amount)
  if ("owner" in p) next.owner = str(p.owner)
  if ("stage" in p) {
    next.stage = str(p.stage)
    if (next.stage && !("view" in p)) next.view = "all"
  }
  return next
}

const FILTER_SPEC = {
  description:
    "Filter the deals table on the dashboard (it is always on screen). Unspecified filters keep " +
    "their current value; reset=true clears all filters first. Returns rows_shown and total.",
  parameters: {
    type: "object",
    properties: {
      view: { type: "string", enum: ["open", "won", "lost", "all"], description: "Deal status tab" },
      min_amount: { type: ["number", "null"], description: "Minimum deal amount in USD; null clears" },
      max_amount: { type: ["number", "null"], description: "Maximum deal amount in USD; null clears" },
      stage: { type: ["string", "null"], enum: [...STAGES, null], description: "Exact pipeline stage" },
      owner: { type: ["string", "null"], description: "Sales rep name (partial match)" },
      search: { type: "string", description: "Text search over account, deal, owner, id" },
      reset: { type: "boolean", description: "Clear all filters before applying these" },
    },
  },
}

export function StageBadge({ stage }: { stage: string }) {
  const variant = stage === "Closed Won" ? "default" : stage === "Closed Lost" ? "destructive" : "outline"
  return <Badge variant={variant}>{stage}</Badge>
}

function SortHeader({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button variant="ghost" size="sm" className="-ml-2 h-8" onClick={onClick}>
      {label}
      <ArrowUpDownIcon />
    </Button>
  )
}

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric },
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
})

const helper = createColumnHelper<typeof features, Deal>()

const columns = helper.columns([
  helper.accessor("name", {
    header: "Deal",
    cell: ({ row }) => (
      <div className="flex flex-col">
        <span className="font-medium">{row.original.account}</span>
        <span className="text-xs text-muted-foreground">
          {row.original.id} · {row.original.name.split(" — ")[1] ?? row.original.name}
        </span>
      </div>
    ),
  }),
  helper.accessor("stage", { header: "Stage", cell: ({ row }) => <StageBadge stage={row.original.stage} /> }),
  helper.accessor("amount_usd", {
    header: ({ column }) => (
      <SortHeader label="Amount" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} />
    ),
    cell: ({ row }) => <span className="tabular-nums">{formatUsd(row.original.amount_usd)}</span>,
  }),
  helper.accessor("probability", {
    header: "Prob.",
    cell: ({ row }) => <span className="tabular-nums">{row.original.probability}%</span>,
  }),
  helper.accessor("close_date", {
    header: ({ column }) => (
      <SortHeader label="Close date" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} />
    ),
    sortFn: "alphanumeric",
  }),
  helper.accessor("owner", { header: "Owner" }),
])

function FilterChips({ filters, onClear }: { filters: DealFilters; onClear: (key: keyof DealFilters) => void }) {
  const chips: Array<[keyof DealFilters, string]> = []
  if (filters.minAmount !== null) chips.push(["minAmount", `Amount ≥ ${formatUsd(filters.minAmount, true)}`])
  if (filters.maxAmount !== null) chips.push(["maxAmount", `Amount ≤ ${formatUsd(filters.maxAmount, true)}`])
  if (filters.stage) chips.push(["stage", `Stage: ${filters.stage}`])
  if (filters.owner) chips.push(["owner", `Owner: ${filters.owner}`])
  if (!chips.length) return null
  return (
    <div className="flex flex-wrap gap-2" data-testid="deals-filter-chips">
      {chips.map(([key, label]) => (
        <Badge key={key} variant="secondary" className="gap-1">
          {label}
          <button type="button" onClick={() => onClear(key)} aria-label={`Clear ${label}`}>
            <XIcon className="size-3" />
          </button>
        </Badge>
      ))}
    </div>
  )
}

export function DealsTable({ deals }: { deals: Deal[] }) {
  const [filters, setFilters] = React.useState<DealFilters>(DEFAULT_FILTERS)
  const [highlight, setHighlight] = React.useState(false)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const filtersRef = React.useRef(filters)
  React.useEffect(() => {
    filtersRef.current = filters
  }, [filters])
  const { publishScreenState } = useRelay()

  const data = React.useMemo(() => filterDeals(deals, filters), [deals, filters])
  const counts = React.useMemo(
    () =>
      Object.fromEntries(
        (Object.keys(VIEWS) as View[]).map((view) => [view, filterDeals(deals, { ...filters, view }).length]),
      ),
    [deals, filters],
  )

  // Tell the agent what the table currently shows.
  React.useEffect(() => {
    publishScreenState("deals_table", { visible: true, filters, rows_shown: data.length, total: deals.length })
  }, [publishScreenState, filters, data.length, deals.length])

  useRelayAction(
    "FILTER_DEALS_TABLE",
    (params) => {
      const next = filtersFromParams(filtersRef.current, params)
      setFilters(next)
      containerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
      setHighlight(true)
      window.setTimeout(() => setHighlight(false), 1600)
      return { rows_shown: filterDeals(deals, next).length, total: deals.length, filters: next }
    },
    FILTER_SPEC,
  )

  const table = useTable({
    features,
    columns,
    data,
    initialState: {
      sorting: [{ id: "close_date", desc: false }],
      pagination: { pageIndex: 0, pageSize: 8 },
    },
  })

  return (
    <div
      ref={containerRef}
      className={cn(
        "flex scroll-mt-4 flex-col gap-4 rounded-lg px-4 transition-shadow duration-500 lg:px-6",
        highlight && "ring-2 ring-primary/40",
      )}
      data-testid="deals-table"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs value={filters.view} onValueChange={(v) => setFilters((f) => ({ ...f, view: v as View }))}>
          <TabsList>
            {(Object.keys(VIEWS) as View[]).map((key) => (
              <TabsTrigger key={key} value={key} className="capitalize">
                {key} <Badge variant="secondary">{counts[key]}</Badge>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Input
          value={filters.search}
          onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          placeholder="Search account, deal or owner…"
          className="h-8 w-full sm:w-64"
        />
      </div>
      <FilterChips
        filters={filters}
        onClear={(key) => setFilters((f) => ({ ...f, [key]: DEFAULT_FILTERS[key] }))}
      />
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader className="bg-muted">
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getAllCells().map((cell) => (
                    <TableCell key={cell.id}>
                      <table.FlexRender cell={cell} />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                  No deals match.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span data-testid="deals-count">{data.length} deals</span>
        <div className="flex items-center gap-2">
          <span>
            Page {table.state.pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}
          </span>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            aria-label="Previous page"
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            aria-label="Next page"
          >
            <ChevronRightIcon />
          </Button>
        </div>
      </div>
    </div>
  )
}
