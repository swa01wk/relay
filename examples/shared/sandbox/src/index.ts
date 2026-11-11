/**
 * Experience Center sandboxes for the Relay example apps (server side only).
 *
 * A visitor gets a random sandbox id in an HttpOnly cookie. The app's server starts every Relay
 * session for `user = { id: "sandbox_<id>" }`, so the example's tools service (which receives the
 * user in the signed `X-Relay-User` header) keeps that visitor's data apart from everyone else's.
 * The browser never chooses the id that reaches the tools service.
 *
 * Use it from two Next.js route handlers:
 *
 *   // app/api/assistant/session/route.ts
 *   export const POST = sandbox.startSession
 *   // app/api/sandbox/reset/route.ts
 *   export const POST = sandbox.reset
 */

export const SANDBOX_COOKIE = "relay_sandbox"
const ID = /^sandbox_[A-Za-z0-9_-]{16,64}$/
const COOKIE_SECONDS = 2 * 60 * 60

export type SandboxConfig = {
  /** Relay gateway base URL, as the app's server reaches it. */
  gatewayUrl: string
  agentId: string
  /** Project id for a local dev gateway (`RELAY_DEV_SESSIONS=1`), used when there is no secret key. */
  projectId: string
  /** Project secret key (`rsk_…`). Required on a hosted gateway; never sent to the browser. */
  secretKey?: string
  /** The example's tools service, for `POST /sandbox/reset`. */
  toolsUrl: string
  /** Sessions one address may start per window (default 20 per 10 minutes). */
  sessionsPerWindow?: number
  windowSeconds?: number
  /** Swap in for tests. */
  fetch?: typeof fetch
}

export type Sandbox = {
  startSession: (request: Request) => Promise<Response>
  reset: (request: Request) => Promise<Response>
}

/**
 * Sandbox mode (the Experience Center deployment) is on when `NEXT_PUBLIC_RELAY_SANDBOX` is
 * 1/true/yes. The same variable tells the app's browser code to get its session from the server.
 */
export function sandboxEnabled(value: string | undefined = process.env.NEXT_PUBLIC_RELAY_SANDBOX): boolean {
  return ["1", "true", "yes"].includes((value ?? "").toLowerCase())
}

/** The visitor's sandbox id from a `Cookie` header (or a cookie value), if well-formed. */
export function sandboxIdFrom(cookieHeaderOrValue: string | null | undefined): string | null {
  if (!cookieHeaderOrValue) return null
  const value = cookieHeaderOrValue.includes("=")
    ? cookieHeaderOrValue
        .split(";")
        .map((part) => part.trim().split("="))
        .find(([name]) => name === SANDBOX_COOKIE)?.[1]
    : cookieHeaderOrValue
  return value && ID.test(value) ? value : null
}

/** A fresh random sandbox id (`sandbox_<32 hex>`). */
export function newSandboxId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return "sandbox_" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
}

/** The `Set-Cookie` value for a sandbox id (attributes depend on HTTP vs HTTPS, see below). */
export function sandboxCookie(id: string, request: Request): string {
  const https = new URL(request.url).protocol === "https:" || request.headers.get("x-forwarded-proto") === "https"
  // Over HTTPS the demo may be framed by the marketing site on another site: a partitioned
  // SameSite=None cookie works there. On http://localhost both are the same site, so Lax is enough.
  const site = https ? "SameSite=None; Secure; Partitioned" : "SameSite=Lax"
  return `${SANDBOX_COOKIE}=${id}; Path=/; HttpOnly; Max-Age=${COOKIE_SECONDS}; ${site}`
}

/** First address in X-Forwarded-For (set by your proxy), else X-Real-IP. */
function clientAddress(request: Request): string {
  return (request.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || request.headers.get("x-real-ip") || "local"
}

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } })

export function createSandbox(config: SandboxConfig): Sandbox {
  const doFetch = config.fetch ?? fetch
  const gateway = config.gatewayUrl.replace(/\/$/, "")
  const maxSessions = config.sessionsPerWindow ?? 20
  const windowMs = (config.windowSeconds ?? 600) * 1000
  const starts = new Map<string, number[]>() // address → start times (one server process)

  const allowed = (address: string, now: number): boolean => {
    const recent = (starts.get(address) ?? []).filter((t) => now - t < windowMs)
    if (recent.length >= maxSessions) {
      starts.set(address, recent)
      return false
    }
    recent.push(now)
    starts.set(address, recent)
    if (starts.size > 10_000) starts.delete(starts.keys().next().value as string)
    return true
  }

  return {
    async startSession(request) {
      if (!allowed(clientAddress(request), Date.now())) {
        return json({ error: "Too many demo sessions from this address. Try again in a few minutes." }, 429, {
          "retry-after": String(config.windowSeconds ?? 600),
        })
      }
      const existing = sandboxIdFrom(request.headers.get("cookie"))
      const id = existing ?? newSandboxId()
      const user = { id }
      const response = config.secretKey
        ? await doFetch(`${gateway}/v1/sessions`, {
            method: "POST",
            headers: { "content-type": "application/json", authorization: `Bearer ${config.secretKey}` },
            body: JSON.stringify({ agent_id: config.agentId, user }),
          })
        : await doFetch(`${gateway}/dev/sessions`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ project_id: config.projectId, agent_id: config.agentId, user }),
          })
      if (!response.ok) {
        return json({ error: `The Relay gateway returned ${response.status}` }, 502)
      }
      const body = (await response.json()) as { session_id: string; token: string }
      // Only the session id and its short-lived token reach the browser.
      return json({ sessionId: body.session_id, token: body.token }, 200, existing ? {} : { "set-cookie": sandboxCookie(id, request) })
    },

    async reset(request) {
      const id = sandboxIdFrom(request.headers.get("cookie"))
      if (!id) return json({ reset: false })
      const response = await doFetch(`${config.toolsUrl.replace(/\/$/, "")}/sandbox/reset`, {
        method: "POST",
        headers: { "x-sandbox-id": id },
      })
      return json({ reset: response.ok }, response.ok ? 200 : 502)
    },
  }
}
