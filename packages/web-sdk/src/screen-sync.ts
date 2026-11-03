/** Keeps screen actions in step with the screen after an action changes it (e.g. a new page). */

type Refresh = () => void;

const refreshers = new WeakMap<object, Set<Refresh>>();

/** Run `refresh` whenever a screen action asks for the actions to be re-read (see below). */
export function onScreenChange(session: object, refresh: Refresh): () => void {
  let set = refreshers.get(session);
  if (!set) refreshers.set(session, (set = new Set()));
  set.add(refresh);
  return () => set.delete(refresh);
}

/**
 * Re-read the screen and re-advertise its actions now. Called before a screen action reports
 * back, so the agent's next step already sees the new page's actions (the socket keeps order).
 */
export function refreshScreenActions(session: object): void {
  for (const refresh of refreshers.get(session) ?? []) refresh();
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Wait until the browser shows `path` and the page has stopped changing (bounded by `timeoutMs`). */
export async function waitForScreen(path: string, { timeoutMs = 3000, quietMs = 150 } = {}): Promise<void> {
  if (typeof location === "undefined") return;
  const started = Date.now();
  while (location.pathname + location.search !== path && Date.now() - started < timeoutMs) await sleep(50);
  if (typeof MutationObserver === "undefined" || typeof document === "undefined") return;
  const left = Math.max(0, timeoutMs - (Date.now() - started));
  await new Promise<void>((resolve) => {
    let quiet = setTimeout(done, quietMs);
    const limit = setTimeout(done, left);
    const observer = new MutationObserver(() => {
      clearTimeout(quiet);
      quiet = setTimeout(done, quietMs);
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    function done() {
      clearTimeout(quiet);
      clearTimeout(limit);
      observer.disconnect();
      resolve();
    }
  });
}
