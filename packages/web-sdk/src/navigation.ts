/** Automatic navigation: the assistant can open any page the app links to, with no route list. */

import { onScreenChange, refreshScreenActions, waitForScreen } from "./screen-sync.js";

export const NAVIGATE_ACTION = "NAVIGATE";

/** A page the assistant may open: an in-app path and the name users know it by. */
export type NavigationPage = {
  path: string;
  title: string;
};

export type AutoNavigationOptions = {
  /**
   * Your router's navigation, e.g. `(path) => router.push(path)`. Recommended for single-page
   * apps. Without it the SDK clicks the page's own link to that path (client-side routers such
   * as Next.js `<Link>` handle that click), or else loads the page (`location.assign`), which
   * ends the session.
   */
  navigate?: (path: string) => void | Promise<void>;
  /** Pages to offer in addition to the links found on screen (e.g. routes not in any menu). */
  pages?: NavigationPage[];
  /** Find pages from the links on screen (default `true`). `false` offers only `pages`. */
  discover?: boolean;
  /** Leave out paths the assistant must never open. Sign-out and similar links are always left out. */
  exclude?: (path: string) => boolean;
  /** Where to look for links (default `document`). */
  root?: ParentNode;
  /** Most pages offered to the assistant (default 60). */
  maxPages?: number;
};

type NavigationSession = {
  registerAction: (
    name: string,
    handler: (
      params: Record<string, unknown>,
      ctx: { actionId: string; name: string },
    ) => void | Record<string, unknown> | Promise<void | Record<string, unknown>>,
    spec?: { description: string; parameters?: Record<string, unknown> },
  ) => () => void;
};

/** The parts of an `<a>` element discovery reads (a real `HTMLAnchorElement` has them all). */
export type NavigationLink = {
  href: string;
  textContent: string | null;
  getAttribute: (name: string) => string | null;
  hasAttribute: (name: string) => boolean;
  click?: () => void;
};

const MAX_TITLE_CHARS = 60;
const DEFAULT_MAX_PAGES = 60;
const NEVER_OPEN = /(^|\/)(log-?out|sign-?out|logoff|sign_out|log_out)(\/|$)/i;
// A path segment that names one record (/orders/1042, /users/3f2a…): those belong to OPEN_<ENTITY>.
const RECORD_SEGMENT = /^(\d+|[0-9a-f]{8,}|[0-9a-f]{8}-[0-9a-f-]{27,}|(?=[a-z0-9_-]*\d)[a-z0-9_-]{16,})$/i;
const REDISCOVER_DELAY_MS = 300;

/** In-app path (`/invoices?tab=open`) of a link, or null when the assistant should not open it. */
export function linkPath(link: NavigationLink, origin: string): string | null {
  if (link.hasAttribute("download")) return null;
  // Placeholders and in-page anchors ("#", "#section", "javascript:…") point at the current page.
  const raw = (link.getAttribute("href") ?? "").trim();
  if (!raw || raw.startsWith("#") || /^javascript:/i.test(raw)) return null;
  const target = link.getAttribute("target");
  if (target && target !== "_self") return null;
  let url: URL;
  try {
    url = new URL(link.href, origin);
  } catch {
    return null;
  }
  if (url.origin !== origin || (url.protocol !== "http:" && url.protocol !== "https:")) return null;
  const path = url.pathname + url.search;
  if (NEVER_OPEN.test(url.pathname)) return null;
  if (url.pathname.split("/").some((segment) => RECORD_SEGMENT.test(segment))) return null;
  return path;
}

function linkTitle(link: NavigationLink, path: string): string {
  const raw = link.getAttribute("aria-label") || link.textContent || link.getAttribute("title") || "";
  const title = raw.replace(/\s+/g, " ").trim();
  return (title || path).slice(0, MAX_TITLE_CHARS);
}

/** Pages from links (first title wins per path) plus `extra`, which overrides titles. */
export function collectPages(
  links: Iterable<NavigationLink>,
  origin: string,
  options: Pick<AutoNavigationOptions, "pages" | "exclude" | "maxPages"> = {},
): NavigationPage[] {
  const max = options.maxPages ?? DEFAULT_MAX_PAGES;
  const pages = new Map<string, string>();
  for (const page of options.pages ?? []) {
    if (page.path.startsWith("/") && !NEVER_OPEN.test(page.path)) {
      pages.set(page.path, page.title.slice(0, MAX_TITLE_CHARS) || page.path);
    }
  }
  for (const link of links) {
    const path = linkPath(link, origin);
    if (!path || pages.has(path) || options.exclude?.(path)) continue;
    pages.set(path, linkTitle(link, path));
  }
  return [...pages]
    .filter(([path]) => !options.exclude?.(path))
    .slice(0, max)
    .map(([path, title]) => ({ path, title }));
}

function navigationSpec(pages: NavigationPage[]) {
  return {
    description:
      "Open a page of the app. Use it when the user asks to go to, open or show a page or section. " +
      "Returns the page now shown.",
    parameters: {
      type: "object",
      properties: {
        path: {
          type: "string",
          enum: pages.map((page) => page.path),
          description: `The page to open. Pages: ${pages.map((page) => `${page.title} = ${page.path}`).join("; ")}`,
        },
      },
      required: ["path"],
    },
  };
}

function findLink(root: ParentNode, path: string, origin: string): NavigationLink | null {
  for (const link of root.querySelectorAll<HTMLAnchorElement>("a[href]")) {
    if (linkPath(link, origin) === path) return link;
  }
  return null;
}

/**
 * Let the assistant open the app's pages. Registers a `NAVIGATE` action over every in-app link on
 * screen (menus, sidebars, tabs) plus `options.pages`, and keeps the list current as the page
 * changes. Links that open one record (`/orders/1042`), sign out, download or open a new tab are
 * left out. Call once after `createRelaySession`; the returned function unregisters it.
 */
export function registerAutoNavigation(
  session: NavigationSession,
  options: AutoNavigationOptions = {},
): () => void {
  if (typeof document === "undefined" || typeof location === "undefined") return () => {};
  const root = options.root ?? document;
  const origin = location.origin;
  const discover = options.discover ?? true;
  let pages: NavigationPage[] = [];
  let signature = "";
  let off: () => void = () => {};

  const handler = async (params: Record<string, unknown>) => {
    const path = String(params.path ?? "");
    const page = pages.find((candidate) => candidate.path === path);
    if (!page) throw new Error(`Unknown page: ${path}`);
    if (location.pathname + location.search === path) return { path, title: page.title, already_open: true };
    if (options.navigate) {
      await options.navigate(path);
    } else {
      const link = findLink(root, path, origin);
      if (!link?.click) {
        location.assign(path); // a full page load; this session ends with the page
        return { path, title: page.title };
      }
      link.click();
    }
    // Report back once the page is there and its actions (forms, filters) are advertised, so the
    // agent can use them in its next step of this same turn.
    await waitForScreen(path);
    refreshScreenActions(session);
    return { path, title: page.title };
  };

  const refresh = () => {
    const links = discover ? root.querySelectorAll<HTMLAnchorElement>("a[href]") : [];
    const next = collectPages(links, origin, options);
    const nextSignature = JSON.stringify(next);
    if (nextSignature === signature) return;
    signature = nextSignature;
    pages = next;
    if (!pages.length) {
      off();
      off = () => {};
      return;
    }
    // Registering again replaces the spec and re-advertises it; the handler stays the same.
    off = session.registerAction(NAVIGATE_ACTION, handler, navigationSpec(pages));
  };

  refresh();
  const offScreenChange = onScreenChange(session, refresh);
  let timer: ReturnType<typeof setTimeout> | undefined;
  const observer =
    discover && typeof MutationObserver !== "undefined"
      ? new MutationObserver(() => {
          clearTimeout(timer);
          timer = setTimeout(refresh, REDISCOVER_DELAY_MS);
        })
      : null;
  observer?.observe("documentElement" in root ? (root as Document).documentElement : (root as Node), {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["href"],
  });

  return () => {
    offScreenChange();
    observer?.disconnect();
    clearTimeout(timer);
    off();
  };
}
