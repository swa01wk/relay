/**
 * Page forms: the assistant can fill the app's own forms on screen. It never submits them, never
 * sees what is typed in them, and never touches passwords, card details or file inputs.
 */

import { onScreenChange } from "./screen-sync.js";

/** Each form on screen is advertised as `PAGE_FORM_<NAME>` (offered to the model as `ui_PAGE_FORM_<NAME>`). */
export const PAGE_FORM_ACTION_PREFIX = "PAGE_FORM_";

export type PageFormsOptions = {
  /** Where to look for forms (default `document`). */
  root?: ParentNode;
  /** Most forms offered at once (default 5). */
  maxForms?: number;
  /** Most fields offered per form (default 30). */
  maxFields?: number;
};

type PageFormsSession = {
  registerAction: (
    name: string,
    handler: (
      params: Record<string, unknown>,
      ctx: { actionId: string; name: string },
    ) => void | Record<string, unknown> | Promise<void | Record<string, unknown>>,
    spec?: { description: string; parameters?: Record<string, unknown> },
  ) => () => void;
};

/** The parts of a form control this module reads and sets (real `<input>`, `<select>` and `<textarea>` have them). */
export type PageFormControl = {
  tagName: string;
  type?: string;
  name?: string;
  id?: string;
  value?: string;
  checked?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  required?: boolean;
  multiple?: boolean;
  maxLength?: number;
  min?: string;
  max?: string;
  placeholder?: string;
  labels?: ArrayLike<{ textContent: string | null }> | null;
  options?: ArrayLike<{ value: string; textContent: string | null; disabled?: boolean }>;
  getAttribute: (name: string) => string | null;
  closest: (selector: string) => unknown;
  click?: () => void;
  dispatchEvent?: (event: Event) => boolean;
  scrollIntoView?: (options?: ScrollIntoViewOptions) => void;
};

/** The parts of a `<form>` this module reads. */
export type PageFormElement = {
  elements: ArrayLike<unknown>;
  getAttribute: (name: string) => string | null;
  closest: (selector: string) => unknown;
  querySelector: (selector: string) => { textContent: string | null } | null;
  getClientRects?: () => ArrayLike<unknown>;
};

type Field = {
  key: string;
  label: string;
  schema: Record<string, unknown>;
  required: boolean;
  controls: PageFormControl[]; // one, or every radio of a group
};

type DiscoveredForm = { name: string; title: string; element: PageFormElement; fields: Field[] };

const IGNORE = "[data-relay-ignore]";
const SKIPPED_TYPES = new Set(["hidden", "password", "file", "submit", "button", "reset", "image"]);
const SENSITIVE_AUTOCOMPLETE = /^(cc-|current-password|new-password|one-time-code)/i;
const SENSITIVE_NAME = /(card|cvv|cvc|iban|ssn|password|passcode|otp|\bpin\b)/i;
const MAX_LABEL_CHARS = 80;
const REDISCOVER_DELAY_MS = 300;

function clean(text: string | null | undefined, max = MAX_LABEL_CHARS): string {
  return (text ?? "").replace(/\s+/g, " ").trim().slice(0, max);
}

function slug(text: string): string {
  return text
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function isSensitive(control: PageFormControl): boolean {
  const autocomplete = control.getAttribute("autocomplete") ?? "";
  return (
    SENSITIVE_AUTOCOMPLETE.test(autocomplete) ||
    SENSITIVE_NAME.test(control.name ?? "") ||
    SENSITIVE_NAME.test(control.id ?? "")
  );
}

function labelOf(control: PageFormControl): string {
  return (
    clean(control.labels?.[0]?.textContent) ||
    clean(control.getAttribute("aria-label")) ||
    clean(control.placeholder) ||
    clean(control.getAttribute("title")) ||
    clean(control.name) ||
    clean(control.id)
  );
}

function controlKind(control: PageFormControl): string {
  const tag = control.tagName.toUpperCase();
  if (tag === "SELECT") return control.multiple ? "unsupported" : "select";
  if (tag === "TEXTAREA") return "text";
  if (tag !== "INPUT") return "unsupported";
  const type = (control.type ?? "text").toLowerCase();
  if (SKIPPED_TYPES.has(type)) return "unsupported";
  if (type === "checkbox" || type === "radio") return type;
  if (type === "number" || type === "range") return "number";
  return type; // text, email, tel, url, search, date, time, datetime-local, month, week, color
}

const FORMAT_HINTS: Record<string, string> = {
  date: "YYYY-MM-DD",
  time: "HH:mm",
  "datetime-local": "YYYY-MM-DDTHH:mm",
  month: "YYYY-MM",
  week: "YYYY-Www",
  color: "#rrggbb",
};

function fieldSchema(kind: string, control: PageFormControl, label: string): Record<string, unknown> {
  if (kind === "checkbox") return { type: "boolean", description: label };
  if (kind === "select") {
    const options = Array.from(control.options ?? []).filter((option) => option.value && !option.disabled);
    const named = options.filter((option) => clean(option.textContent) && clean(option.textContent) !== option.value);
    const names = named.length ? ` (${named.map((option) => `${option.value} = ${clean(option.textContent, 40)}`).join("; ")})` : "";
    return { type: "string", enum: options.map((option) => option.value), description: `${label}${names}` };
  }
  if (kind === "number") {
    const schema: Record<string, unknown> = { type: "number", description: label };
    if (control.min !== undefined && control.min !== "") schema.minimum = Number(control.min);
    if (control.max !== undefined && control.max !== "") schema.maximum = Number(control.max);
    return schema;
  }
  const hint = FORMAT_HINTS[kind];
  const schema: Record<string, unknown> = { type: "string", description: hint ? `${label} (${hint})` : label };
  if (kind === "email") schema.format = "email";
  if (control.maxLength && control.maxLength > 0) schema.maxLength = control.maxLength;
  return schema;
}

function radioGroupLabel(control: PageFormControl): string {
  const fieldset = control.closest("fieldset") as { querySelector?: (s: string) => { textContent: string | null } | null } | null;
  return clean(fieldset?.querySelector?.("legend")?.textContent) || clean(control.name) || labelOf(control);
}

/** Fillable fields of a form, in order. Passwords, card details, files, hidden and read-only fields are left out. */
export function formFields(form: PageFormElement, maxFields = 30): Field[] {
  const fields: Field[] = [];
  const byKey = new Map<string, Field>();
  for (const item of Array.from(form.elements)) {
    const control = item as PageFormControl;
    if (!control || typeof control.tagName !== "string" || typeof control.getAttribute !== "function") continue;
    const kind = controlKind(control);
    if (kind === "unsupported" || control.disabled || control.readOnly) continue;
    if (control.closest(IGNORE) || isSensitive(control)) continue;
    if (kind === "radio") {
      const key = control.name || control.id || "";
      if (!key) continue;
      const group = byKey.get(key);
      if (group) {
        group.controls.push(control);
        (group.schema.enum as string[]).push(control.value ?? "");
        group.required ||= Boolean(control.required);
        continue;
      }
      const label = radioGroupLabel(control);
      const field = { key, label, schema: { type: "string", enum: [control.value ?? ""], description: label }, required: Boolean(control.required), controls: [control] };
      byKey.set(key, field);
      fields.push(field);
      continue;
    }
    const label = labelOf(control);
    let key = control.name || control.id || slug(label).toLowerCase();
    if (!key) continue;
    if (byKey.has(key)) key = `${key}_${fields.length + 1}`;
    const field = { key, label: label || key, schema: fieldSchema(kind, control, label || key), required: Boolean(control.required), controls: [control] };
    byKey.set(key, field);
    fields.push(field);
  }
  return fields.slice(0, maxFields);
}

function formTitle(form: PageFormElement, index: number): string {
  const labelledBy = form.getAttribute("aria-labelledby");
  const doc = typeof document !== "undefined" ? document : null;
  return (
    clean(form.getAttribute("data-relay-form")) ||
    clean(form.getAttribute("aria-label")) ||
    (labelledBy && doc ? clean(doc.getElementById(labelledBy)?.textContent) : "") ||
    clean(form.querySelector("legend, h1, h2, h3, h4")?.textContent) ||
    clean(form.getAttribute("name")) ||
    clean(form.getAttribute("id")) ||
    `Form ${index + 1}`
  );
}

function isVisible(form: PageFormElement): boolean {
  return typeof form.getClientRects === "function" ? form.getClientRects().length > 0 : true;
}

/**
 * Forms on screen worth offering: visible, outside `data-relay-ignore` (put it on the assistant's
 * own panel and canvas), with no password field (sign-in forms) and at least two fillable fields
 * (a lone search box or chat input is not a form to fill). `data-relay-form="Title"` names a form
 * and keeps it even with one field.
 */
export function discoverForms(forms: Iterable<PageFormElement>, options: Pick<PageFormsOptions, "maxForms" | "maxFields"> = {}): DiscoveredForm[] {
  const found: DiscoveredForm[] = [];
  const used = new Set<string>();
  let index = 0;
  for (const form of forms) {
    const position = index++;
    if (form.closest(IGNORE) || !isVisible(form)) continue;
    const controls = Array.from(form.elements) as PageFormControl[];
    if (controls.some((c) => c && typeof c.type === "string" && c.type.toLowerCase() === "password")) continue;
    const fields = formFields(form, options.maxFields);
    if (fields.length < (form.getAttribute("data-relay-form") ? 1 : 2)) continue;
    const title = formTitle(form, position);
    const base = `${PAGE_FORM_ACTION_PREFIX}${slug(title) || `FORM_${position + 1}`}`.slice(0, 56);
    let name = base;
    for (let n = 2; used.has(name); n += 1) name = `${base}_${n}`;
    used.add(name);
    found.push({ name, title, element: form, fields });
    if (found.length >= (options.maxForms ?? 5)) break;
  }
  return found;
}

function formSpec(form: DiscoveredForm) {
  return {
    description: `Fill the "${form.title.slice(0, 60)}" form on the user's screen. Does not submit: the user reviews and submits it. Returns the fields filled and any rejected.`,
    // No JSON-schema `required`: filling only some fields is fine; the form's own rules are in the text.
    parameters: {
      type: "object",
      properties: Object.fromEntries(
        form.fields.map((field) => [
          field.key,
          field.required ? { ...field.schema, description: `${field.schema.description} (required by the form)` } : field.schema,
        ]),
      ),
    },
  };
}

function setNativeValue(control: PageFormControl, value: string): void {
  // React and similar libraries track the value on the instance; set it through the element's
  // own prototype setter and fire the events they listen to, or they ignore the change.
  const proto = Object.getPrototypeOf(control);
  const setter = proto ? Object.getOwnPropertyDescriptor(proto, "value")?.set : undefined;
  if (setter) setter.call(control, value);
  else control.value = value;
  if (control.dispatchEvent && typeof Event !== "undefined") {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }
}

const DATE_LIKE: Record<string, RegExp> = {
  date: /^\d{4}-\d{2}-\d{2}$/,
  time: /^\d{2}:\d{2}(:\d{2})?$/,
  "datetime-local": /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/,
  month: /^\d{4}-\d{2}$/,
};

/** Put one value into a field; returns a reason when it cannot be used. */
export function fillField(field: Field, value: unknown): string | null {
  const control = field.controls[0];
  const kind = controlKind(control);
  if (kind === "checkbox") {
    const wanted = value === true || value === "true" || value === 1;
    if (Boolean(control.checked) !== wanted) {
      if (control.click) control.click(); // a click is what frameworks listen to for checkboxes
      else control.checked = wanted;
    }
    return null;
  }
  if (value === null || value === undefined || typeof value === "object") return "expected a single value";
  const text = String(value);
  if (kind === "radio") {
    const option = field.controls.find((radio) => radio.value === text);
    if (!option) return `not one of: ${field.controls.map((radio) => radio.value).join(", ")}`;
    if (!option.checked) {
      if (option.click) option.click();
      else option.checked = true;
    }
    return null;
  }
  if (kind === "select") {
    const options = Array.from(control.options ?? []);
    const match =
      options.find((option) => option.value === text) ??
      options.find((option) => clean(option.textContent).toLowerCase() === text.trim().toLowerCase());
    if (!match || match.disabled) return `not one of the choices`;
    setNativeValue(control, match.value);
    return null;
  }
  if (kind === "number" && !Number.isFinite(Number(text))) return "expected a number";
  if (DATE_LIKE[kind] && !DATE_LIKE[kind].test(text)) return `expected ${FORMAT_HINTS[kind]}`;
  const max = control.maxLength && control.maxLength > 0 ? control.maxLength : undefined;
  setNativeValue(control, max ? text.slice(0, max) : text);
  return null;
}

/**
 * Let the assistant fill the app's own forms on screen ("fill this form", or after opening a page
 * with `registerAutoNavigation`). Each form becomes a `PAGE_FORM_<NAME>` action whose parameters
 * are the form's fields (labels, choices, limits — never their current values). Filling sets the
 * fields the way typing would; it never submits. Call once after `createRelaySession`; the
 * returned function unregisters it.
 */
export function registerPageForms(session: PageFormsSession, options: PageFormsOptions = {}): () => void {
  if (typeof document === "undefined") return () => {};
  const root = options.root ?? document;
  let forms: DiscoveredForm[] = [];
  const registered = new Map<string, { signature: string; off: () => void }>();
  const handlers = new Map<string, (params: Record<string, unknown>) => Record<string, unknown>>();

  const handlerFor = (name: string) => {
    let handler = handlers.get(name);
    if (!handler) {
      handler = (params: Record<string, unknown>) => {
        const form = forms.find((candidate) => candidate.name === name);
        if (!form) throw new Error("That form is no longer on the screen");
        const filled: string[] = [];
        const rejected: Record<string, string> = {};
        for (const [key, value] of Object.entries(params)) {
          const field = form.fields.find((candidate) => candidate.key === key);
          const reason = field ? fillField(field, value) : "no such field";
          if (reason) rejected[key] = reason;
          else filled.push(field!.label);
        }
        const first = form.fields.find((field) => field.key in params)?.controls[0];
        first?.scrollIntoView?.({ block: "center", behavior: "smooth" });
        const missing = form.fields.filter((field) => field.required && !(field.key in params)).map((field) => field.label);
        return {
          form: form.title,
          filled,
          ...(Object.keys(rejected).length ? { rejected } : {}),
          ...(missing.length ? { still_required: missing } : {}),
          submitted: false,
        };
      };
      handlers.set(name, handler);
    }
    return handler;
  };

  const refresh = () => {
    forms = discoverForms(root.querySelectorAll<HTMLFormElement>("form") as Iterable<unknown> as Iterable<PageFormElement>, options);
    const current = new Set(forms.map((form) => form.name));
    for (const [name, entry] of registered) {
      if (!current.has(name)) {
        entry.off();
        registered.delete(name);
      }
    }
    for (const form of forms) {
      const spec = formSpec(form);
      const signature = JSON.stringify(spec);
      if (registered.get(form.name)?.signature === signature) continue;
      registered.set(form.name, { signature, off: session.registerAction(form.name, handlerFor(form.name), spec) });
    }
  };

  refresh();
  const offScreenChange = onScreenChange(session, refresh);
  let timer: ReturnType<typeof setTimeout> | undefined;
  const observer =
    typeof MutationObserver !== "undefined"
      ? new MutationObserver(() => {
          clearTimeout(timer);
          timer = setTimeout(refresh, REDISCOVER_DELAY_MS);
        })
      : null;
  observer?.observe("documentElement" in root ? (root as Document).documentElement : (root as Node), {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["name", "id", "disabled", "readonly", "required", "type", "hidden", "data-relay-ignore", "data-relay-form"],
  });

  return () => {
    offScreenChange();
    observer?.disconnect();
    clearTimeout(timer);
    for (const entry of registered.values()) entry.off();
    registered.clear();
  };
}
