"use client";

import {
  ArrowRightIcon,
  CalendarIcon,
  ClipboardCheckIcon,
  HistoryIcon,
  HomeIcon,
  PercentIcon,
  SearchIcon,
  UserIcon,
  WalletIcon,
} from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { MortgageUiState } from "@/lib/mortgage-ui-state";

/**
 * The servicing workspace: one view per `MortgageUiState.screen`. The agent changes the screen
 * through registered actions (SHOW_SEARCH_RESULTS, OPEN_ENTITY, SHOW_CORRECTION_DRAFT,
 * SHOW_RATE_HISTORY); these components only render that state.
 */

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
const money = (value: unknown) => usd.format(Number(value ?? 0));
const pct = (value: unknown) => `${Number(value ?? 0).toFixed(3)}%`;
const reasonLabel = (reason: unknown) => String(reason ?? "").replace(/_/g, " ");

const screenMeta: Record<MortgageUiState["screen"], { label: string; icon: typeof HomeIcon }> = {
  home: { label: "Overview", icon: HomeIcon },
  search_results: { label: "Customer search", icon: SearchIcon },
  mortgage_case: { label: "Mortgage case", icon: WalletIcon },
  correction_draft: { label: "Rate correction", icon: ClipboardCheckIcon },
  rate_history: { label: "Rate history", icon: HistoryIcon },
};

export function WorkspaceHeader({ state }: { state: MortgageUiState }) {
  const meta = screenMeta[state.screen];
  const Icon = meta.icon;
  const caseId = state.selected_entity?.id ?? (state.case_summary?.id as string | undefined);
  const customer = state.case_summary?.customer_name as string | undefined;
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
      <Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />
      <span className="font-medium">{meta.label}</span>
      {customer && state.screen !== "search_results" && (
        <>
          <span className="text-muted-foreground">/</span>
          <span className="truncate text-muted-foreground">{customer}</span>
        </>
      )}
      {caseId && state.screen !== "search_results" && state.screen !== "home" && (
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">{caseId}</span>
      )}
    </nav>
  );
}

export function HomeView({
  connected,
  connecting,
  onAsk,
  onConnect,
}: {
  connected: boolean;
  connecting: boolean;
  onAsk: (text: string) => void;
  onConnect: () => void;
}) {
  const starters = [
    { text: "Find Rajesh Sharma", hint: "Look up a borrower and open the active loan" },
    { text: "Show rate history", hint: "Every rate change on the open loan" },
    { text: "Compare last 3 months payments", hint: "Table on the results canvas" },
    { text: "Prepare correction draft", hint: "Draft → approval → commit → verify" },
  ];
  return (
    <div className="flex flex-col items-start gap-6 py-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Good to see you.</h2>
        <p className="mt-1 max-w-lg text-sm text-muted-foreground">
          Ask the assistant to find a borrower, explain their payments or draft a rate correction. It works this
          screen for you — nothing is changed without your approval.
        </p>
      </div>
      <ul className="grid w-full gap-3 sm:grid-cols-2">
        {starters.map((s) => (
          <li key={s.text}>
            <button
              type="button"
              disabled={!connected}
              onClick={() => onAsk(s.text)}
              className="group flex w-full items-start gap-3 rounded-lg border bg-card p-4 text-left transition hover:border-primary/40 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="flex-1">
                <span className="block text-sm font-medium">&ldquo;{s.text}&rdquo;</span>
                <span className="mt-1 block text-xs text-muted-foreground">{s.hint}</span>
              </span>
              <ArrowRightIcon className="mt-0.5 size-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
            </button>
          </li>
        ))}
      </ul>
      {!connected && (
        <button
          type="button"
          disabled={connecting}
          onClick={onConnect}
          className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {connecting ? "Connecting…" : "Connect assistant"}
        </button>
      )}
    </div>
  );
}

export function SearchResultsView({
  state,
  onOpen,
}: {
  state: MortgageUiState;
  onOpen: (mortgageId: string) => void;
}) {
  return (
    <div className="space-y-3" data-testid="search-results-view">
      <p className="text-sm text-muted-foreground">
        {state.search_results.length} result{state.search_results.length === 1 ? "" : "s"} for{" "}
        <span className="font-medium text-foreground">&ldquo;{state.search_query}&rdquo;</span>
      </p>
      <ul className="space-y-3">
        {state.search_results.map((c) => {
          const mortgages = (c.mortgages as Array<Record<string, unknown>> | undefined) ?? [];
          return (
            <li key={String(c.id)} data-testid="search-result-row" className="rounded-lg border bg-card">
              <div className="flex items-center gap-3 border-b px-4 py-3">
                <span className="grid size-9 place-items-center rounded-full bg-primary-soft text-sm font-semibold text-primary">
                  {String(c.name ?? "?")
                    .split(" ")
                    .map((part) => part[0])
                    .join("")
                    .slice(0, 2)}
                </span>
                <div className="min-w-0">
                  <p className="font-medium">{String(c.name)}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {String(c.id)}
                    {c.email ? ` · ${String(c.email)}` : ""}
                  </p>
                </div>
              </div>
              <ul className="divide-y">
                {mortgages.map((m) => (
                  <li key={String(m.id)}>
                    <button
                      type="button"
                      onClick={() => onOpen(String(m.id))}
                      className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-left text-sm hover:bg-muted/60"
                    >
                      <span className="font-mono text-xs">{String(m.id)}</span>
                      <span className="min-w-0 flex-1 truncate text-muted-foreground">{String(m.property ?? "")}</span>
                      <span className="tabular">{pct(m.current_rate)}</span>
                      <Badge tone={statusTone(String(m.status ?? ""))}>{String(m.status ?? "")}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
  testId,
  sub,
}: {
  label: string;
  value: string;
  icon: typeof HomeIcon;
  testId?: string;
  sub?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Icon className="size-3.5" aria-hidden="true" /> {label}
      </p>
      <p className="tabular mt-2 text-2xl font-semibold tracking-tight" data-testid={testId}>
        {value}
      </p>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function CaseView({ state }: { state: MortgageUiState }) {
  const c = state.case_summary ?? {};
  const status = String(c.status ?? "unknown");
  return (
    <div className="space-y-4" data-testid="mortgage-case-view">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs text-muted-foreground">Case {String(c.id)}</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight">{String(c.customer_name ?? "Borrower")}</h2>
          {c.property ? <p className="mt-0.5 text-sm text-muted-foreground">{String(c.property)}</p> : null}
        </div>
        <Badge tone={statusTone(status)}>{status}</Badge>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {/* Plain toFixed (no thousands separator): the e2e specs look for e.g. "2847.50". */}
        <Stat label="Current rate" icon={PercentIcon} value={`${Number(c.current_rate ?? 0).toFixed(3)}%`} testId="case-current-rate" />
        <Stat label="Monthly payment (EMI)" icon={WalletIcon} value={`$${Number(c.emi ?? 0).toFixed(2)}`} testId="case-current-emi" />
        <Stat label="Borrower" icon={UserIcon} value={String(c.customer_id ?? "—")} />
      </div>
    </div>
  );
}

export function CorrectionDraftView({
  state,
  onEffectiveDateChange,
}: {
  state: MortgageUiState;
  onEffectiveDateChange: (value: string) => void;
}) {
  const d = state.correction_draft ?? {};
  const status = String(d.status ?? "draft");
  const delta = Number(d.estimated_emi_delta ?? 0);
  return (
    <div className="space-y-4" data-testid="correction-draft-view">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1">
          <p className="font-mono text-xs text-muted-foreground">Draft correction — {String(d.mortgage_id ?? "")}</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight">Rate correction</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Edit the effective date here or tell the assistant. Committing needs your approval.
          </p>
        </div>
        <Badge tone={statusTone(status)} data-testid="draft-status">
          Status: {status}
        </Badge>
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-stretch">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">Today</p>
          <p className="tabular mt-2 text-lg font-semibold">{pct(d.current_rate)}</p>
          <p className="tabular text-sm text-muted-foreground">{money(d.current_emi)} / month</p>
        </div>
        <div className="hidden items-center text-muted-foreground sm:flex" aria-hidden="true">
          <ArrowRightIcon className="size-5" />
        </div>
        <div className="rounded-lg border border-primary/30 bg-primary-soft/50 p-4">
          <p className="text-xs font-medium text-primary">After correction</p>
          <p className="tabular mt-2 text-lg font-semibold">{pct(d.proposed_rate)}</p>
          <p className="tabular text-sm" data-testid="correction-projected-emi">
            Projected EMI: ${Number(d.projected_emi ?? 0).toFixed(2)}
          </p>
          <p className={`tabular text-xs ${delta > 0 ? "text-danger" : delta < 0 ? "text-success" : "text-muted-foreground"}`}>
            {delta > 0 ? "+" : ""}
            {money(delta)} vs today
          </p>
        </div>
      </div>

      <label className="flex max-w-xs flex-col gap-1.5">
        <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <CalendarIcon className="size-3.5" aria-hidden="true" /> Effective date
        </span>
        <Input
          data-testid="correction-effective-date"
          value={String(d.effective_date ?? "")}
          onChange={(e) => onEffectiveDateChange(e.target.value)}
          className="font-mono"
        />
      </label>
    </div>
  );
}

export function RateHistoryView({ state }: { state: MortgageUiState }) {
  const rows = state.rate_history;
  return (
    <div className="space-y-3" data-testid="rate-history-view">
      <h2 className="text-lg font-semibold tracking-tight">Rate history</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No rate changes on record.</p>
      ) : (
        <ol className="relative space-y-4 border-l pl-6">
          {rows.map((row, idx) => {
            const previous = idx > 0 ? Number(rows[idx - 1].rate) : null;
            const change = previous === null ? null : Number(row.rate) - previous;
            return (
              <li key={`${String(row.effective_date)}-${idx}`} className="relative">
                <span
                  className={`absolute -left-[1.85rem] top-1 size-3 rounded-full border-2 border-card ${idx === rows.length - 1 ? "bg-primary" : "bg-border"}`}
                  aria-hidden="true"
                />
                <p className="font-mono text-xs text-muted-foreground">{String(row.effective_date)}</p>
                <p className="mt-0.5 flex flex-wrap items-baseline gap-2">
                  <span className="tabular text-base font-semibold">{String(row.rate)}%</span>
                  {change !== null && (
                    <span className={`tabular text-xs ${change > 0 ? "text-danger" : "text-success"}`}>
                      {change > 0 ? "▲" : "▼"} {Math.abs(change).toFixed(3)}
                    </span>
                  )}
                  <span className="text-sm capitalize text-muted-foreground">({reasonLabel(row.reason)})</span>
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
