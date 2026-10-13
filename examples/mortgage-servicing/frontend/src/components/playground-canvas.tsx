"use client";

import { useMemo, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  surfaceToCsv,
  type PresentUiParams,
  type UiComparisonSurface,
  type UiFormSurface,
  type UiSurface,
  type UiTableSurface,
} from "@sumukhj1219-wkt-org/relay-web-sdk";

import { PlaygroundChart } from "@/components/playground-chart";

export type FormValues = Record<string, string | number | boolean | null>;
export type SubmitFormHandler = (form: UiFormSurface, values: FormValues) => void;

/** Apply a PRESENT_UI payload: replace the canvas, or append (same surface id updates in place). */
export function applyPresentUi(current: UiSurface[], params: PresentUiParams): UiSurface[] {
  if (params.replace) return params.surfaces;
  const next = [...current];
  for (const surface of params.surfaces) {
    const index = surface.id ? next.findIndex((s) => s.id === surface.id) : -1;
    if (index >= 0) next[index] = surface;
    else next.push(surface);
  }
  return next;
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function compareCells(a: unknown, b: unknown): number {
  const na = Number(a);
  const nb = Number(b);
  if (a !== "" && b !== "" && Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
  return cellText(a).localeCompare(cellText(b), undefined, { numeric: true });
}

function downloadCsv(surface: UiSurface, rows?: Array<Record<string, unknown>>) {
  const csv = surfaceToCsv(surface, rows);
  if (!csv) return;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${(surface.title ?? surface.kind).replace(/[^\w-]+/g, "_").toLowerCase()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function CsvButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted"
      data-testid="playground-export-csv"
    >
      Export CSV
    </button>
  );
}

function TableView({ surface }: { surface: UiTableSurface }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? surface.rows.filter((row) =>
          surface.columns.some((col) => cellText(row[col.key]).toLowerCase().includes(needle)),
        )
      : surface.rows;
    if (!sort) return filtered;
    return [...filtered].sort((a, b) => compareCells(a[sort.key], b[sort.key]) * sort.dir);
  }, [surface, query, sort]);

  const toggleSort = (key: string) =>
    setSort((prev) => (prev?.key !== key ? { key, dir: 1 } : prev.dir === 1 ? { key, dir: -1 } : null));

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter rows…"
          className="h-7 flex-1 rounded border px-2 text-xs"
          data-testid="playground-table-filter"
        />
        <span className="text-xs text-muted-foreground" data-testid="playground-table-count">
          {rows.length}/{surface.rows.length}
        </span>
        <CsvButton onClick={() => downloadCsv(surface, rows)} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm" data-testid="playground-table">
          {surface.caption && (
            <caption className="pb-1 text-left text-xs text-muted-foreground">{surface.caption}</caption>
          )}
          <thead>
            <tr className="border-b">
              {surface.columns.map((col) => (
                <th key={col.key} className="px-2 py-1 text-left font-medium">
                  <button
                    type="button"
                    onClick={() => toggleSort(col.key)}
                    className="hover:underline"
                    aria-sort={
                      sort?.key === col.key ? (sort.dir === 1 ? "ascending" : "descending") : undefined
                    }
                  >
                    {col.label}
                    {sort?.key === col.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b last:border-0">
                {surface.columns.map((col) => (
                  <td key={col.key} className="px-2 py-1">
                    {cellText(row[col.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ComparisonView({ surface }: { surface: UiComparisonSurface }) {
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <CsvButton onClick={() => downloadCsv(surface)} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm" data-testid="playground-comparison">
          <thead>
            <tr className="border-b">
              <th className="px-2 py-1 text-left font-medium text-muted-foreground">Field</th>
              {surface.entities.map((name) => (
                <th key={name} className="px-2 py-1 text-left font-medium">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {surface.rows.map((row) => (
              <tr
                key={row.label}
                className={`border-b last:border-0 ${row.differs ? "bg-amber-50" : ""}`}
                data-differs={row.differs}
              >
                <td className="px-2 py-1 text-muted-foreground">{row.label}</td>
                {row.values.map((value, index) => (
                  <td key={index} className={`px-2 py-1 ${row.differs ? "font-medium" : ""}`}>
                    {value}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">Highlighted rows differ.</p>
    </div>
  );
}

function initialFormValues(form: UiFormSurface): FormValues {
  return Object.fromEntries(
    form.fields.map((field) => [
      field.name,
      field.defaultValue ?? (field.type === "checkbox" ? false : ""),
    ]),
  );
}

function FormView({ surface, onSubmit }: { surface: UiFormSurface; onSubmit?: SubmitFormHandler }) {
  const [values, setValues] = useState<FormValues>(() => initialFormValues(surface));
  const [submitted, setSubmitted] = useState(false);
  const set = (name: string, value: string | number | boolean | null) =>
    setValues((prev) => ({ ...prev, [name]: value }));

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!onSubmit || submitted) return;
    const out: FormValues = {};
    for (const field of surface.fields) {
      const value = values[field.name];
      out[field.name] =
        field.type === "number" ? (value === "" || value === null ? null : Number(value)) : value;
    }
    onSubmit(surface, out);
    setSubmitted(true);
  };

  const inputClass = "h-8 w-full rounded border px-2 text-sm disabled:opacity-60";
  return (
    <form onSubmit={handleSubmit} className="space-y-3" data-testid="playground-form" data-form-id={surface.id}>
      {surface.description && <p className="text-sm text-muted-foreground">{surface.description}</p>}
      <fieldset disabled={submitted} className="grid gap-3 sm:grid-cols-2">
        {surface.fields.map((field) => {
          const id = `${surface.id}-${field.name}`;
          const value = values[field.name];
          const label = (
            <label htmlFor={id} className="text-xs text-muted-foreground">
              {field.label}
              {field.required ? " *" : ""}
            </label>
          );
          if (field.type === "checkbox") {
            return (
              <div key={field.name} className="flex items-center gap-2 sm:col-span-2">
                <input
                  id={id}
                  type="checkbox"
                  checked={Boolean(value)}
                  onChange={(e) => set(field.name, e.target.checked)}
                />
                {label}
              </div>
            );
          }
          return (
            <div key={field.name} className={`space-y-1 ${field.type === "textarea" ? "sm:col-span-2" : ""}`}>
              {label}
              {field.type === "select" ? (
                <select
                  id={id}
                  required={field.required}
                  value={String(value ?? "")}
                  onChange={(e) => set(field.name, e.target.value)}
                  className={inputClass}
                >
                  <option value="">Select…</option>
                  {field.options?.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              ) : field.type === "textarea" ? (
                <textarea
                  id={id}
                  required={field.required}
                  placeholder={field.placeholder}
                  value={String(value ?? "")}
                  onChange={(e) => set(field.name, e.target.value)}
                  className="min-h-16 w-full rounded border px-2 py-1 text-sm disabled:opacity-60"
                />
              ) : (
                <input
                  id={id}
                  type={field.type}
                  required={field.required}
                  placeholder={field.placeholder}
                  value={String(value ?? "")}
                  onChange={(e) => set(field.name, e.target.value)}
                  className={inputClass}
                />
              )}
            </div>
          );
        })}
      </fieldset>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitted || !onSubmit}
          className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground disabled:opacity-50"
        >
          {surface.submitLabel}
        </button>
        {submitted && (
          <span className="text-xs text-muted-foreground" data-testid="playground-form-submitted">
            Submitted
          </span>
        )}
      </div>
    </form>
  );
}

function SurfaceView({ surface, onSubmitForm }: { surface: UiSurface; onSubmitForm?: SubmitFormHandler }) {
  switch (surface.kind) {
    case "table":
      return <TableView surface={surface} />;
    case "kv":
      return (
        <div className="space-y-2">
          <div className="flex justify-end">
            <CsvButton onClick={() => downloadCsv(surface)} />
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            {surface.items.map((item, index) => (
              <div key={`${item.label}-${index}`} className="contents">
                <dt className="text-muted-foreground">{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      );
    case "cards":
      return (
        <div className="grid gap-2 sm:grid-cols-2">
          {surface.cards.map((card, index) => (
            <div key={`${card.title}-${index}`} className="rounded-md border p-2 text-sm">
              <p className="font-medium">{card.title}</p>
              {card.body && <p className="text-muted-foreground">{card.body}</p>}
              {card.fields?.map((field) => (
                <p key={field.label} className="text-xs">
                  <span className="text-muted-foreground">{field.label}:</span> {field.value}
                </p>
              ))}
            </div>
          ))}
        </div>
      );
    case "notice":
      return <p className="text-sm">{surface.body}</p>;
    case "chart":
      return (
        <div className="space-y-1">
          <div className="flex justify-end">
            <CsvButton onClick={() => downloadCsv(surface)} />
          </div>
          <PlaygroundChart surface={surface} />
        </div>
      );
    case "comparison":
      return <ComparisonView surface={surface} />;
    case "markdown":
      return (
        // react-markdown skips raw HTML by default, so model output cannot inject markup.
        <div className="relay-markdown text-sm" data-testid="playground-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{surface.markdown}</ReactMarkdown>
        </div>
      );
    case "form":
      return <FormView key={surface.id} surface={surface} onSubmit={onSubmitForm} />;
  }
}

export function PlaygroundCanvas({
  surfaces,
  onSubmitForm,
}: {
  surfaces: UiSurface[];
  onSubmitForm?: SubmitFormHandler;
}) {
  return (
    <div className="rounded-md border p-3 md:col-span-2" data-testid="playground-canvas">
      <p className="text-xs font-medium text-muted-foreground">Playground</p>
      {surfaces.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">
          Ask for a table, chart, comparison or details — e.g. &quot;chart my payments by month&quot;.
        </p>
      ) : (
        <div className="mt-2 space-y-4">
          {surfaces.map((surface, index) => (
            <section key={surface.id ?? index} data-testid="playground-surface" data-kind={surface.kind}>
              {surface.title && <p className="mb-1 text-sm font-medium">{surface.title}</p>}
              <SurfaceView surface={surface} onSubmitForm={onSubmitForm} />
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
