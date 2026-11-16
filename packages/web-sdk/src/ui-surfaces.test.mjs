import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizePresentUiParams,
  registerFormFill,
  registerPlaygroundSurfaces,
  submitForm,
  surfaceToCsv,
} from "./ui-surfaces.ts";

test("normalizes SHOW_TABLE-shaped payload into a table surface", () => {
  const result = normalizePresentUiParams({
    title: "Payments",
    columns: ["month", "amount"],
    rows: [
      { month: "2025-09", amount: 2847.5 },
      ["2025-08", 2847.5],
    ],
  });
  assert.equal(result.surfaces.length, 1);
  assert.equal(result.surfaces[0].kind, "table");
  if (result.surfaces[0].kind !== "table") return;
  assert.equal(result.surfaces[0].title, "Payments");
  assert.equal(result.surfaces[0].rows.length, 2);
  assert.equal(result.surfaces[0].rows[1].month, "2025-08");
});

test("registerPlaygroundSurfaces wires PRESENT_UI and SHOW_TABLE", async () => {
  const handlers = new Map();
  const session = {
    registerAction: (name, handler) => {
      handlers.set(name, handler);
      return () => handlers.delete(name);
    },
  };
  const seen = [];
  const off = registerPlaygroundSurfaces(session, (params) => {
    seen.push(params);
  });
  await handlers.get("SHOW_TABLE")(
    { title: "Demo", columns: [{ key: "id", label: "ID" }], rows: [{ id: "1" }] },
    { actionId: "a1", name: "SHOW_TABLE" },
  );
  assert.equal(seen[0].surfaces[0].kind, "table");
  if (seen[0].surfaces[0].kind === "table") {
    assert.equal(seen[0].surfaces[0].rows[0].id, "1");
  }
  off();
  assert.equal(handlers.size, 0);
});

test("chart surface keeps explicit spec and coerces numeric strings", () => {
  const { surfaces } = normalizePresentUiParams({
    surfaces: [{
      kind: "chart",
      chart_type: "line",
      title: "Rate trend",
      x_key: "effective_date",
      series: [{ key: "rate", label: "Rate" }],
      data: [
        { effective_date: "2023-06-01", rate: "5.5" },
        { effective_date: "2025-01-01", rate: 6.125 },
      ],
    }],
  });
  const chart = surfaces[0];
  assert.equal(chart.kind, "chart");
  if (chart.kind !== "chart") return;
  assert.equal(chart.chartType, "line");
  assert.equal(chart.xKey, "effective_date");
  assert.deepEqual(chart.data.map((d) => d.rate), [5.5, 6.125]);
});

test("chart surface infers x axis and numeric series when the model omits them", () => {
  const { surfaces } = normalizePresentUiParams({
    surfaces: [{
      kind: "graph",
      data: [
        { month: "2025-08", amount: "$2,847.50", late_fee: 0, status: "paid" },
        { month: "2025-09", amount: 2847.5, late_fee: 25, status: "late" },
      ],
    }],
  });
  const chart = surfaces[0];
  if (chart.kind !== "chart") throw new Error("expected chart");
  assert.equal(chart.chartType, "bar");
  assert.equal(chart.xKey, "month");
  assert.deepEqual(chart.series.map((s) => s.key), ["amount", "late_fee"]);
  assert.equal(chart.data[0].amount, 2847.5);
});

test("comparison lines entities up by field and flags differing rows", () => {
  const { surfaces } = normalizePresentUiParams({
    surfaces: [{
      kind: "comparison",
      title: "Loans",
      compare: [
        { name: "MORT-2931", fields: { status: "active", current_rate: 6.125, city: "Austin" } },
        { name: "MORT-1102", fields: { status: "closed", current_rate: 4.875, city: "Austin" } },
      ],
    }],
  });
  const cmp = surfaces[0];
  if (cmp.kind !== "comparison") throw new Error("expected comparison");
  assert.deepEqual(cmp.entities, ["MORT-2931", "MORT-1102"]);
  const byLabel = Object.fromEntries(cmp.rows.map((r) => [r.label, r]));
  assert.equal(byLabel["Current Rate"].differs, true);
  assert.equal(byLabel["City"].differs, false);
});

test("markdown kind stays markdown", () => {
  const { surfaces } = normalizePresentUiParams({ surfaces: [{ kind: "markdown", markdown: "# Hi" }] });
  assert.equal(surfaces[0].kind, "markdown");
});

test("form normalizes fields and submitForm sends ui.form_submit", () => {
  const { surfaces } = normalizePresentUiParams({
    surfaces: [{
      kind: "form",
      id: "contact",
      title: "Update contact",
      fields: [
        { name: "email", label: "Email", type: "email", required: true },
        { name: "channel", options: ["email", "phone"] },
        { name: "", type: "text" },
      ],
    }],
  });
  const form = surfaces[0];
  if (form.kind !== "form") throw new Error("expected form");
  assert.deepEqual(form.fields.map((f) => [f.name, f.type, f.required]), [
    ["email", "email", true],
    ["channel", "select", false],
  ]);
  const sent = [];
  submitForm({ sendEvent: (name, payload) => sent.push([name, payload]) }, form, { email: "a@b.co" });
  assert.deepEqual(sent, [["ui.form_submit", { form_id: "contact", title: "Update contact", values: { email: "a@b.co" } }]]);
});

test("form without usable fields is dropped", () => {
  const { surfaces } = normalizePresentUiParams({ surfaces: [{ kind: "form", fields: [] }] });
  assert.equal(surfaces.length, 0);
});

test("surfaceToCsv escapes commas, quotes and uses filtered rows when given", () => {
  const { surfaces } = normalizePresentUiParams({
    title: "T",
    columns: ["name", "note"],
    rows: [{ name: "Rajesh", note: 'says "hi", ok' }, { name: "Maria", note: "x" }],
  });
  const table = surfaces[0];
  assert.equal(surfaceToCsv(table), 'Name,Note\r\nRajesh,"says ""hi"", ok"\r\nMaria,x\r\n');
  assert.equal(surfaceToCsv(table, [{ name: "Maria", note: "x" }]), "Name,Note\r\nMaria,x\r\n");
});

test("tool-bound form keeps submitTool", () => {
  const { surfaces } = normalizePresentUiParams({
    surfaces: [{ kind: "form", id: "log_activity-1", submit_tool: "log_activity", fields: [{ name: "subject", type: "text" }] }],
  });
  assert.equal(surfaces[0].submitTool, "log_activity");
});

test("registerFormFill hands the app the form id and values, and reports what was filled", async () => {
  const handlers = new Map();
  const session = { registerAction: (name, handler) => (handlers.set(name, handler), () => handlers.delete(name)) };
  const fills = [];
  const off = registerFormFill(session, (fill) => {
    if (fill.formId !== "report") throw new Error("form not open");
    fills.push(fill);
  });
  const result = await handlers.get("FILL_FORM")(
    { form_id: "report", values: { summary: "Crash", people: 3, urgent: true, junk: { nested: 1 } } },
    { actionId: "a1", name: "FILL_FORM" },
  );
  assert.deepEqual(fills, [{ formId: "report", values: { summary: "Crash", people: 3, urgent: true } }]);
  assert.deepEqual(result, { form_id: "report", filled: ["summary", "people", "urgent"] });
  await assert.rejects(handlers.get("FILL_FORM")({ form_id: "gone", values: { a: "b" } }, { actionId: "a2", name: "FILL_FORM" }), /form not open/);
  off();
  assert.equal(handlers.size, 0);
});
