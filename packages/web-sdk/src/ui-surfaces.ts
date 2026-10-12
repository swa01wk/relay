/** Generative playground surfaces over RP `ACTION_REQUESTED` (app still owns pixels). */

export const PRESENT_UI_ACTION = "PRESENT_UI";
export const SHOW_TABLE_ACTION = "SHOW_TABLE";
/** APP_EVENT name the runtime turns into the next user turn. */
export const FORM_SUBMIT_EVENT = "ui.form_submit";

export type UiTableColumn = { key: string; label: string };

export type UiTableSurface = {
  kind: "table";
  id?: string;
  title?: string;
  caption?: string;
  columns: UiTableColumn[];
  rows: Array<Record<string, unknown>>;
};

export type UiKeyValueSurface = {
  kind: "kv";
  id?: string;
  title?: string;
  items: Array<{ label: string; value: string }>;
};

export type UiCardsSurface = {
  kind: "cards";
  id?: string;
  title?: string;
  cards: Array<{
    title: string;
    body?: string;
    fields?: Array<{ label: string; value: string }>;
  }>;
};

export type UiNoticeSurface = {
  kind: "notice";
  id?: string;
  title?: string;
  body: string;
};

export type UiChartType = "bar" | "line" | "area" | "pie";

export type UiChartSurface = {
  kind: "chart";
  id?: string;
  title?: string;
  caption?: string;
  chartType: UiChartType;
  /** Field on each data point used for the x axis (or pie slice labels). */
  xKey: string;
  /** Numeric fields to plot; pie uses the first. */
  series: Array<{ key: string; label: string }>;
  data: Array<Record<string, string | number | null>>;
  yLabel?: string;
  stacked?: boolean;
};

export type UiComparisonSurface = {
  kind: "comparison";
  id?: string;
  title?: string;
  /** Entity names, one column each. */
  entities: string[];
  /** One row per field; `differs` marks rows whose values are not all equal. */
  rows: Array<{ label: string; values: string[]; differs: boolean }>;
};

export type UiMarkdownSurface = {
  kind: "markdown";
  id?: string;
  title?: string;
  markdown: string;
};

export type UiFormFieldType = "text" | "textarea" | "number" | "date" | "email" | "select" | "checkbox";

export type UiFormField = {
  name: string;
  label: string;
  type: UiFormFieldType;
  required: boolean;
  options?: string[];
  defaultValue?: string | number | boolean;
  placeholder?: string;
};

export type UiFormSurface = {
  kind: "form";
  id: string;
  title?: string;
  description?: string;
  fields: UiFormField[];
  submitLabel: string;
  /** Set when submitting saves through this backend write tool (otherwise values go to the assistant). */
  submitTool?: string;
};

export type UiSurface =
  | UiTableSurface
  | UiKeyValueSurface
  | UiCardsSurface
  | UiNoticeSurface
  | UiChartSurface
  | UiComparisonSurface
  | UiMarkdownSurface
  | UiFormSurface;

export type PresentUiParams = {
  surfaces: UiSurface[];
  replace: boolean;
};

export type PlaygroundSession = {
  registerAction: (
    name: string,
    handler: (
      params: Record<string, unknown>,
      ctx: { actionId: string; name: string },
    ) => void | Promise<void>,
  ) => () => void;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function labelFromKey(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function stringifyCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function normalizeColumns(raw: unknown, sampleRow: Record<string, unknown>): UiTableColumn[] {
  if (Array.isArray(raw) && raw.length > 0) {
    return raw.map((col, index) => {
      if (typeof col === "string") {
        return { key: col, label: labelFromKey(col) };
      }
      const rec = asRecord(col);
      const key = String(rec.key ?? rec.id ?? rec.field ?? `col_${index}`);
      return { key, label: String(rec.label ?? rec.title ?? labelFromKey(key)) };
    });
  }
  return Object.keys(sampleRow).map((key) => ({ key, label: labelFromKey(key) }));
}

function normalizeRows(raw: unknown, columns: UiTableColumn[]): Array<Record<string, unknown>> {
  if (!Array.isArray(raw)) return [];
  return raw.map((row) => {
    if (Array.isArray(row)) {
      const rec: Record<string, unknown> = {};
      columns.forEach((col, i) => {
        rec[col.key] = row[i];
      });
      return rec;
    }
    return asRecord(row);
  });
}

export function normalizeTableSurface(params: Record<string, unknown>): UiTableSurface {
  const nested = asRecord(params.table);
  const source = Object.keys(nested).length ? { ...params, ...nested } : params;
  const rawRows = source.rows ?? source.data ?? source.records;
  const preview = Array.isArray(rawRows) && rawRows[0] !== undefined ? asRecord(rawRows[0]) : {};
  const columns = normalizeColumns(source.columns, preview);
  return {
    kind: "table",
    id: source.id ? String(source.id) : undefined,
    title: source.title ? String(source.title) : "Table",
    caption: source.caption ? String(source.caption) : undefined,
    columns,
    rows: normalizeRows(rawRows, columns),
  };
}

function normalizeKvSurface(params: Record<string, unknown>): UiKeyValueSurface {
  const itemsRaw = params.items ?? params.fields ?? params.pairs;
  const items: Array<{ label: string; value: string }> = [];
  if (Array.isArray(itemsRaw)) {
    for (const item of itemsRaw) {
      const rec = asRecord(item);
      const label = String(rec.label ?? rec.key ?? rec.name ?? "");
      items.push({ label, value: stringifyCell(rec.value ?? rec.text) });
    }
  } else if (itemsRaw && typeof itemsRaw === "object") {
    for (const [key, value] of Object.entries(asRecord(itemsRaw))) {
      items.push({ label: labelFromKey(key), value: stringifyCell(value) });
    }
  }
  return {
    kind: "kv",
    id: params.id ? String(params.id) : undefined,
    title: params.title ? String(params.title) : "Details",
    items,
  };
}

function normalizeCardsSurface(params: Record<string, unknown>): UiCardsSurface {
  const raw = Array.isArray(params.cards) ? params.cards : [];
  return {
    kind: "cards",
    id: params.id ? String(params.id) : undefined,
    title: params.title ? String(params.title) : "Cards",
    cards: raw.map((card) => {
      const rec = asRecord(card);
      const fieldsRaw = rec.fields;
      let fields: Array<{ label: string; value: string }> | undefined;
      if (Array.isArray(fieldsRaw)) {
        fields = fieldsRaw.map((field) => {
          const f = asRecord(field);
          return {
            label: String(f.label ?? f.key ?? ""),
            value: stringifyCell(f.value),
          };
        });
      } else if (fieldsRaw && typeof fieldsRaw === "object") {
        fields = Object.entries(asRecord(fieldsRaw)).map(([key, value]) => ({
          label: labelFromKey(key),
          value: stringifyCell(value),
        }));
      }
      return {
        title: String(rec.title ?? rec.name ?? rec.id ?? "Item"),
        body: rec.body ? String(rec.body) : undefined,
        fields,
      };
    }),
  };
}

function normalizeNoticeSurface(params: Record<string, unknown>): UiNoticeSurface {
  return {
    kind: "notice",
    id: params.id ? String(params.id) : undefined,
    title: params.title ? String(params.title) : undefined,
    body: String(params.body ?? params.text ?? params.message ?? ""),
  };
}

const CHART_TYPES: readonly UiChartType[] = ["bar", "line", "area", "pie"];

function toNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const parsed = Number(value.replace(/[$,%\s]/g, ""));
    return value.trim() !== "" && Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function normalizeSeries(raw: unknown): Array<{ key: string; label: string }> {
  const list = Array.isArray(raw) ? raw : raw ? [raw] : [];
  return list
    .map((item) => {
      if (typeof item === "string") return { key: item, label: labelFromKey(item) };
      const rec = asRecord(item);
      const key = String(rec.key ?? rec.field ?? rec.dataKey ?? "");
      return { key, label: String(rec.label ?? rec.name ?? labelFromKey(key)) };
    })
    .filter((item) => item.key);
}

export function normalizeChartSurface(params: Record<string, unknown>): UiChartSurface {
  const nested = asRecord(params.chart);
  const source = Object.keys(nested).length ? { ...params, ...nested } : params;
  const rawData = source.data ?? source.rows ?? source.points ?? [];
  const points = (Array.isArray(rawData) ? rawData : []).map(asRecord);
  const sample = points[0] ?? {};
  const keys = Object.keys(sample);

  let xKey = String(source.x_key ?? source.xKey ?? source.x ?? source.category ?? "");
  if (!xKey || !keys.includes(xKey)) {
    xKey = keys.find((key) => toNumber(sample[key]) === null) ?? keys[0] ?? "x";
  }
  let series = normalizeSeries(source.series ?? source.y_keys ?? source.yKeys ?? source.y);
  if (series.length === 0) {
    series = keys
      .filter((key) => key !== xKey && toNumber(sample[key]) !== null)
      .map((key) => ({ key, label: labelFromKey(key) }));
  }

  const data = points.map((point) => {
    const row: Record<string, string | number | null> = { [xKey]: stringifyCell(point[xKey]) };
    for (const { key } of series) row[key] = toNumber(point[key]);
    return row;
  });

  const requested = String(source.chart_type ?? source.chartType ?? source.type ?? "").toLowerCase();
  const chartType = (CHART_TYPES as readonly string[]).includes(requested)
    ? (requested as UiChartType)
    : "bar";

  return {
    kind: "chart",
    id: source.id ? String(source.id) : undefined,
    title: source.title ? String(source.title) : "Chart",
    caption: source.caption ? String(source.caption) : undefined,
    chartType,
    xKey,
    series,
    data,
    yLabel: source.y_label || source.yLabel ? String(source.y_label ?? source.yLabel) : undefined,
    stacked: Boolean(source.stacked),
  };
}

function normalizeComparisonSurface(params: Record<string, unknown>): UiComparisonSurface {
  const raw = params.compare ?? params.items ?? params.entities ?? [];
  const items = (Array.isArray(raw) ? raw : []).map(asRecord);
  const entities = items.map((item, i) => String(item.name ?? item.title ?? item.id ?? `Item ${i + 1}`));
  const fieldsOf = (item: Record<string, unknown>) => {
    const fields = asRecord(item.fields ?? item.values ?? {});
    return Object.keys(fields).length ? fields : item;
  };
  const labels: string[] = [];
  for (const item of items) {
    for (const key of Object.keys(fieldsOf(item))) {
      if (["name", "title"].includes(key) && !item.fields) continue;
      if (!labels.includes(key)) labels.push(key);
    }
  }
  const rows = labels.map((key) => {
    const values = items.map((item) => stringifyCell(fieldsOf(item)[key]));
    return { label: labelFromKey(key), values, differs: new Set(values).size > 1 };
  });
  return {
    kind: "comparison",
    id: params.id ? String(params.id) : undefined,
    title: params.title ? String(params.title) : "Comparison",
    entities,
    rows,
  };
}

function normalizeMarkdownSurface(params: Record<string, unknown>): UiMarkdownSurface {
  return {
    kind: "markdown",
    id: params.id ? String(params.id) : undefined,
    title: params.title ? String(params.title) : undefined,
    markdown: String(params.markdown ?? params.body ?? params.text ?? ""),
  };
}

const FORM_FIELD_TYPES: readonly UiFormFieldType[] = [
  "text", "textarea", "number", "date", "email", "select", "checkbox",
];

function normalizeFormSurface(params: Record<string, unknown>): UiFormSurface {
  const raw = Array.isArray(params.fields) ? params.fields : [];
  const fields: UiFormField[] = raw
    .map(asRecord)
    .filter((field) => field.name)
    .map((field) => {
      const name = String(field.name);
      const requested = String(field.type ?? "").toLowerCase() as UiFormFieldType;
      const options = Array.isArray(field.options) ? field.options.map(String) : undefined;
      const type = FORM_FIELD_TYPES.includes(requested) ? requested : options ? "select" : "text";
      const def = field.default ?? field.defaultValue;
      return {
        name,
        label: String(field.label ?? labelFromKey(name)),
        type,
        required: Boolean(field.required),
        options,
        defaultValue:
          typeof def === "string" || typeof def === "number" || typeof def === "boolean" ? def : undefined,
        placeholder: field.placeholder ? String(field.placeholder) : undefined,
      };
    });
  return {
    kind: "form",
    id: String(params.id ?? "form"),
    title: params.title ? String(params.title) : "Form",
    description: params.description ? String(params.description) : undefined,
    fields,
    submitLabel: String(params.submit_label ?? params.submitLabel ?? "Submit"),
    submitTool: params.submit_tool || params.submitTool ? String(params.submit_tool ?? params.submitTool) : undefined,
  };
}

export function normalizeUiSurface(raw: unknown): UiSurface | null {
  const params = asRecord(raw);
  const kind = String(params.kind ?? params.type ?? "").toLowerCase();
  if (kind === "chart" || kind === "graph" || params.chart_type || params.chartType) {
    return normalizeChartSurface(params);
  }
  if (kind === "comparison" || kind === "compare" || params.compare) {
    return normalizeComparisonSurface(params);
  }
  if (kind === "form") {
    const form = normalizeFormSurface(params);
    return form.fields.length ? form : null;
  }
  if (kind === "markdown" || kind === "md") {
    return normalizeMarkdownSurface(params);
  }
  if (kind === "table" || params.columns || params.rows) {
    return normalizeTableSurface(params);
  }
  if (kind === "kv" || kind === "key_value" || kind === "fields") {
    return normalizeKvSurface(params);
  }
  if (kind === "cards" || kind === "card") {
    return normalizeCardsSurface(params);
  }
  if (kind === "notice" || kind === "text") {
    return normalizeNoticeSurface(params);
  }
  if (params.title || params.body || params.message) {
    return normalizeNoticeSurface(params);
  }
  return null;
}

export function normalizePresentUiParams(params: Record<string, unknown>): PresentUiParams {
  const replace = Boolean(params.replace ?? true);
  if (Array.isArray(params.surfaces)) {
    const surfaces = params.surfaces
      .map((item) => normalizeUiSurface(item))
      .filter((item): item is UiSurface => item !== null);
    return { surfaces, replace };
  }
  const single = normalizeUiSurface(params);
  return { surfaces: single ? [single] : [], replace };
}

export function registerPlaygroundSurfaces(
  session: PlaygroundSession,
  onPresent: (
    params: PresentUiParams,
    ctx: { actionId: string; name: string },
  ) => void | Promise<void>,
): () => void {
  const handle = async (params: Record<string, unknown>, ctx: { actionId: string; name: string }) => {
    await onPresent(normalizePresentUiParams(params), ctx);
  };
  const offPresent = session.registerAction(PRESENT_UI_ACTION, handle);
  const offTable = session.registerAction(SHOW_TABLE_ACTION, async (params, ctx) => {
    await onPresent(
      { surfaces: [normalizeTableSurface(params)], replace: Boolean(params.replace ?? true) },
      ctx,
    );
  });
  return () => {
    offPresent();
    offTable();
  };
}


type AppEventSender = { sendEvent: (name: string, payload?: Record<string, unknown>) => void };

/**
 * Send a form's values back. Forms with `submitTool` are saved by the runtime through that tool
 * (watch `COMMIT_VERIFIED` / `ERROR` with `payload.form_id`); others become the user's next turn.
 */
export function submitForm(
  session: AppEventSender,
  form: Pick<UiFormSurface, "id" | "title">,
  values: Record<string, string | number | boolean | null>,
): void {
  session.sendEvent(FORM_SUBMIT_EVENT, { form_id: form.id, title: form.title, values });
}

function csvCell(value: unknown): string {
  const text = stringifyCell(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** CSV for table, chart and comparison surfaces (null for kinds without tabular data). */
export function surfaceToCsv(
  surface: UiSurface,
  rows?: Array<Record<string, unknown>>,
): string | null {
  const lines: unknown[][] = [];
  if (surface.kind === "table") {
    lines.push(surface.columns.map((c) => c.label));
    for (const row of rows ?? surface.rows) lines.push(surface.columns.map((c) => row[c.key]));
  } else if (surface.kind === "chart") {
    lines.push([surface.xKey, ...surface.series.map((s) => s.label)]);
    for (const point of surface.data) lines.push([point[surface.xKey], ...surface.series.map((s) => point[s.key])]);
  } else if (surface.kind === "comparison") {
    lines.push(["Field", ...surface.entities]);
    for (const row of surface.rows) lines.push([row.label, ...row.values]);
  } else if (surface.kind === "kv") {
    lines.push(["Label", "Value"]);
    for (const item of surface.items) lines.push([item.label, item.value]);
  } else {
    return null;
  }
  return lines.map((line) => line.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
