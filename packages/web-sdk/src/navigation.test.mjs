import test from "node:test";
import assert from "node:assert/strict";
import { NAVIGATE_ACTION, collectPages, linkPath, registerAutoNavigation } from "../dist/navigation.js";
import { onScreenChange } from "../dist/screen-sync.js";

const ORIGIN = "https://app.test";

function link(href, text = "", attrs = {}) {
  const all = { href, ...attrs };
  return {
    href: href.startsWith("#") || !href ? `${ORIGIN}/dashboard${href}` : href,   // what a browser resolves
    textContent: text,
    getAttribute: (name) => all[name] ?? null,
    hasAttribute: (name) => name in attrs,
    clicked: 0,
    click() {
      this.clicked += 1;
    },
  };
}

test("linkPath keeps in-app pages and drops records, sign-out, other sites, downloads and new tabs", () => {
  assert.equal(linkPath(link("/invoices"), ORIGIN), "/invoices");
  assert.equal(linkPath(link("https://app.test/reports?tab=open"), ORIGIN), "/reports?tab=open");
  assert.equal(linkPath(link("/orders/1042"), ORIGIN), null);
  assert.equal(linkPath(link("/users/3f2a9c1e-77aa-4b1c-9d2e-0a1b2c3d4e5f"), ORIGIN), null);
  assert.equal(linkPath(link("/logout"), ORIGIN), null);
  assert.equal(linkPath(link("/auth/sign-out"), ORIGIN), null);
  assert.equal(linkPath(link("https://other.test/pricing"), ORIGIN), null);
  assert.equal(linkPath(link("mailto:help@app.test"), ORIGIN), null);
  assert.equal(linkPath(link("/export.csv", "", { download: "" }), ORIGIN), null);
  assert.equal(linkPath(link("/docs", "", { target: "_blank" }), ORIGIN), null);
  assert.equal(linkPath(link("/settings", "", { target: "_self" }), ORIGIN), "/settings");
});

test("linkPath drops placeholder and in-page links, which point at the current page", () => {
  assert.equal(linkPath(link("#", "Deals"), ORIGIN), null);
  assert.equal(linkPath(link("#pipeline", "Pipeline"), ORIGIN), null);
  assert.equal(linkPath(link("", "Empty"), ORIGIN), null);
  assert.equal(linkPath(link("javascript:void(0)", "Menu"), ORIGIN), null);
});

test("collectPages dedupes by path, names pages from their link text, and adds explicit pages first", () => {
  const pages = collectPages(
    [
      link("/", "  Dashboard\n "),
      link("/invoices", "Invoices"),
      link("/invoices", "See all invoices"),
      link("/settings", "", { "aria-label": "Settings" }),
      link("/help"),
    ],
    ORIGIN,
    { pages: [{ path: "/reports/annual", title: "Annual report" }], exclude: (path) => path === "/help" },
  );
  assert.deepEqual(pages, [
    { path: "/reports/annual", title: "Annual report" },
    { path: "/", title: "Dashboard" },
    { path: "/invoices", title: "Invoices" },
    { path: "/settings", title: "Settings" },
  ]);
  assert.equal(collectPages([link("/a"), link("/b"), link("/c")], ORIGIN, { maxPages: 2 }).length, 2);
});

function fakeBrowser(links, path = "/") {
  const assigned = [];
  for (const each of links) {
    const click = each.click;
    each.click = function () {
      click.call(this);
      globalThis.location.pathname = new URL(this.href, ORIGIN).pathname;   // the router changes page
    };
  }
  globalThis.document = { querySelectorAll: () => links };
  globalThis.location = {
    origin: ORIGIN,
    pathname: path,
    search: "",
    assign: (to) => assigned.push(to),
  };
  return {
    assigned,
    restore() {
      delete globalThis.document;
      delete globalThis.location;
    },
  };
}

function fakeSession() {
  const registered = [];
  return {
    registered,
    registerAction(name, handler, spec) {
      registered.push({ name, handler, spec });
      return () => registered.push({ name, removed: true });
    },
  };
}

test("registerAutoNavigation advertises NAVIGATE over the pages and opens one by clicking its link", async () => {
  const invoices = link("/invoices", "Invoices");
  const browser = fakeBrowser([link("/", "Dashboard"), invoices, link("/orders/77", "Order 77")]);
  try {
    const session = fakeSession();
    const off = registerAutoNavigation(session);
    const [{ name, handler, spec }] = session.registered;
    assert.equal(name, NAVIGATE_ACTION);
    assert.deepEqual(spec.parameters.properties.path.enum, ["/", "/invoices"]);
    assert.match(spec.parameters.properties.path.description, /Invoices = \/invoices/);

    const refreshed = [];
    onScreenChange(session, () => refreshed.push(location.pathname));
    assert.deepEqual(await handler({ path: "/invoices" }), { path: "/invoices", title: "Invoices" });
    assert.equal(invoices.clicked, 1);
    // The new page's actions (forms, filters) were re-read before NAVIGATE reported back.
    assert.deepEqual(refreshed, ["/invoices"]);
    assert.deepEqual(await handler({ path: "/invoices" }), { path: "/invoices", title: "Invoices", already_open: true });
    await assert.rejects(handler({ path: "/orders/77" }), /Unknown page/);

    off();
    assert.deepEqual(session.registered.at(-1), { name: NAVIGATE_ACTION, removed: true });
  } finally {
    browser.restore();
  }
});

test("registerAutoNavigation uses the app's router when given, and only explicit pages without discovery", async () => {
  const browser = fakeBrowser([link("/invoices", "Invoices")]);
  try {
    const session = fakeSession();
    const routed = [];
    registerAutoNavigation(session, {
      discover: false,
      pages: [{ path: "/billing", title: "Billing" }],
      navigate: (path) => {
        routed.push(path);
        location.pathname = path;
      },
    });
    const [{ handler, spec }] = session.registered;
    assert.deepEqual(spec.parameters.properties.path.enum, ["/billing"]);
    await handler({ path: "/billing" });
    assert.deepEqual(routed, ["/billing"]);
    assert.deepEqual(browser.assigned, []);
  } finally {
    browser.restore();
  }
});

test("registerAutoNavigation loads the page when no link or router can open it", async () => {
  const browser = fakeBrowser([]);
  try {
    const session = fakeSession();
    registerAutoNavigation(session, { pages: [{ path: "/billing", title: "Billing" }] });
    await session.registered[0].handler({ path: "/billing" });
    assert.deepEqual(browser.assigned, ["/billing"]);
  } finally {
    browser.restore();
  }
});

test("registerAutoNavigation does nothing outside a browser (server rendering)", () => {
  const session = fakeSession();
  const off = registerAutoNavigation(session);
  assert.equal(session.registered.length, 0);
  off();
});
