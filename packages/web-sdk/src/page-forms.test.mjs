import test from "node:test";
import assert from "node:assert/strict";
import { discoverForms, fillField, formFields, registerPageForms } from "../dist/page-forms.js";

function control(tagName, props = {}, attrs = {}) {
  const el = {
    tagName,
    type: tagName === "INPUT" ? "text" : undefined,
    name: "",
    id: "",
    value: "",
    checked: false,
    disabled: false,
    readOnly: false,
    required: false,
    maxLength: -1,
    placeholder: "",
    labels: null,
    events: [],
    ignored: false,
    getAttribute: (name) => attrs[name] ?? null,
    closest(selector) {
      return selector === "[data-relay-ignore]" && this.ignored ? {} : null;
    },
    dispatchEvent(event) {
      this.events.push(event.type);
      return true;
    },
    click() {
      if (this.type === "radio") this.checked = true;
      else this.checked = !this.checked;
    },
    ...props,
  };
  if (props.label) el.labels = [{ textContent: props.label }];
  return el;
}

function form(elements, attrs = {}, extra = {}) {
  return {
    elements,
    getAttribute: (name) => attrs[name] ?? null,
    closest: () => null,
    querySelector: () => (extra.heading ? { textContent: extra.heading } : null),
    ...extra,
  };
}

const option = (value, textContent = value, disabled = false) => ({ value, textContent, disabled });

function invoiceForm() {
  return form(
    [
      control("INPUT", { name: "customer", label: "Customer", required: true }),
      control("INPUT", { name: "amount", type: "number", label: "Amount", min: "0" }),
      control("INPUT", { name: "due", type: "date", label: "Due date" }),
      control("SELECT", { name: "status", label: "Status", options: [option(""), option("draft", "Draft"), option("sent", "Sent")] }),
      control("TEXTAREA", { name: "notes", label: "Notes", maxLength: 10 }),
      control("INPUT", { name: "urgent", type: "checkbox", label: "Urgent" }),
      control("INPUT", { name: "terms", type: "radio", value: "net30" }),
      control("INPUT", { name: "terms", type: "radio", value: "net60" }),
      control("INPUT", { name: "csrf", type: "hidden", value: "secret" }),
      control("INPUT", { name: "card_number", label: "Card" }),
      control("INPUT", { name: "cvc_code", label: "CVC", getAttribute: (n) => (n === "autocomplete" ? "cc-csc" : null) }),
      control("INPUT", { name: "attachment", type: "file" }),
      control("INPUT", { name: "ref", label: "Reference", readOnly: true }),
      control("INPUT", { name: "internal", label: "Internal", ignored: true }),
      control("BUTTON", { type: "submit" }),
    ],
    {},
    { heading: "New invoice" },
  );
}

test("formFields describes fillable fields and leaves out hidden, sensitive, file, read-only and ignored ones", () => {
  const fields = formFields(invoiceForm());
  assert.deepEqual(fields.map((f) => f.key), ["customer", "amount", "due", "status", "notes", "urgent", "terms"]);
  const byKey = Object.fromEntries(fields.map((f) => [f.key, f]));
  assert.deepEqual(byKey.amount.schema, { type: "number", description: "Amount", minimum: 0 });
  assert.equal(byKey.due.schema.description, "Due date (YYYY-MM-DD)");
  assert.deepEqual(byKey.status.schema.enum, ["draft", "sent"]);
  assert.match(byKey.status.schema.description, /draft = Draft/);
  assert.equal(byKey.notes.schema.maxLength, 10);
  assert.equal(byKey.urgent.schema.type, "boolean");
  assert.deepEqual(byKey.terms.schema.enum, ["net30", "net60"]);
  assert.equal(byKey.customer.required, true);
});

test("discoverForms skips sign-in forms, single-field forms, ignored and hidden forms, and names the rest", () => {
  const login = form([control("INPUT", { name: "email" }), control("INPUT", { name: "pw", type: "password" })]);
  const chat = form([control("TEXTAREA", { name: "message", label: "Message" })]);
  const named = form([control("INPUT", { name: "q", label: "Search" })], { "data-relay-form": "Quick search" });
  const ignored = { ...invoiceForm(), closest: () => ({}) };
  const hidden = { ...invoiceForm(), getClientRects: () => [] };
  const found = discoverForms([login, chat, invoiceForm(), named, ignored, hidden, invoiceForm()]);
  assert.deepEqual(found.map((f) => f.name), ["PAGE_FORM_NEW_INVOICE", "PAGE_FORM_QUICK_SEARCH", "PAGE_FORM_NEW_INVOICE_2"]);
  assert.equal(found[0].title, "New invoice");
});

test("fillField sets values the way typing does and rejects values the form would not accept", () => {
  const fields = Object.fromEntries(formFields(invoiceForm()).map((f) => [f.key, f]));
  assert.equal(fillField(fields.customer, "Acme"), null);
  assert.equal(fields.customer.controls[0].value, "Acme");
  assert.deepEqual(fields.customer.controls[0].events, ["input", "change"]);
  assert.equal(fillField(fields.status, "Sent"), null);             // by its visible label
  assert.equal(fields.status.controls[0].value, "sent");
  assert.equal(fillField(fields.status, "paid"), "not one of the choices");
  assert.equal(fillField(fields.amount, "lots"), "expected a number");
  assert.equal(fillField(fields.due, "next friday"), "expected YYYY-MM-DD");
  assert.equal(fillField(fields.due, "2026-12-01"), null);
  assert.equal(fillField(fields.notes, "a very long note"), null);
  assert.equal(fields.notes.controls[0].value, "a very lon");      // cut at the field's maxLength
  assert.equal(fillField(fields.urgent, true), null);
  assert.equal(fields.urgent.controls[0].checked, true);
  assert.equal(fillField(fields.urgent, true), null);               // already checked: not toggled off
  assert.equal(fields.urgent.controls[0].checked, true);
  assert.equal(fillField(fields.terms, "net60"), null);
  assert.equal(fields.terms.controls[1].checked, true);
  assert.match(fillField(fields.terms, "net90"), /not one of: net30, net60/);
});

test("registerPageForms advertises each form and fills it without submitting", async () => {
  const invoice = invoiceForm();
  globalThis.document = { querySelectorAll: () => [invoice] };
  try {
    const registered = [];
    const session = {
      registerAction(name, handler, spec) {
        registered.push({ name, handler, spec });
        return () => registered.push({ name, removed: true });
      },
    };
    const off = registerPageForms(session);
    const [{ name, handler, spec }] = registered;
    assert.equal(name, "PAGE_FORM_NEW_INVOICE");
    assert.match(spec.description, /Does not submit/);
    assert.equal(spec.parameters.required, undefined);   // filling some fields is fine
    assert.match(spec.parameters.properties.customer.description, /required by the form/);
    assert.equal(JSON.stringify(spec).includes("secret"), false);  // current values never leave the page

    const result = await handler({ customer: "Acme", amount: 50000, status: "paid", nope: 1 });
    assert.deepEqual(result, {
      form: "New invoice",
      filled: ["Customer", "Amount"],
      rejected: { status: "not one of the choices", nope: "no such field" },
      submitted: false,
    });
    off();
    assert.deepEqual(registered.at(-1), { name: "PAGE_FORM_NEW_INVOICE", removed: true });
  } finally {
    delete globalThis.document;
  }
});
