import assert from "node:assert/strict"
import { test } from "node:test"

import { createSandbox, SANDBOX_COOKIE, sandboxIdFrom } from "./index.ts"

type Call = { url: string; init: RequestInit }

function fakeGateway(calls: Call[], status = 200) {
  return (async (url: string, init: RequestInit) => {
    calls.push({ url, init })
    return new Response(JSON.stringify({ session_id: "s1", token: "t1" }), { status })
  }) as unknown as typeof fetch
}

const base = { gatewayUrl: "http://gw/", agentId: "crm", projectId: "proj", toolsUrl: "http://tools" }

test("a new visitor gets a sandbox cookie and a session started for that sandbox", async () => {
  const calls: Call[] = []
  const sandbox = createSandbox({ ...base, fetch: fakeGateway(calls) })
  const res = await sandbox.startSession(new Request("http://app/api/assistant/session", { method: "POST" }))
  assert.equal(res.status, 200)
  assert.deepEqual(await res.json(), { sessionId: "s1", token: "t1" })
  const id = sandboxIdFrom(res.headers.get("set-cookie")!.split(";")[0])!
  assert.match(id, /^sandbox_[0-9a-f]{32}$/)
  assert.match(res.headers.get("set-cookie")!, /HttpOnly; Max-Age=7200; SameSite=Lax/)
  assert.equal(calls[0].url, "http://gw/dev/sessions")
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), { project_id: "proj", agent_id: "crm", user: { id } })
})

test("a returning visitor keeps their sandbox; a secret key uses /v1/sessions", async () => {
  const calls: Call[] = []
  const sandbox = createSandbox({ ...base, secretKey: "rsk_x", fetch: fakeGateway(calls) })
  const id = "sandbox_" + "a".repeat(32)
  const res = await sandbox.startSession(
    new Request("https://app/api/assistant/session", { method: "POST", headers: { cookie: `x=1; ${SANDBOX_COOKIE}=${id}` } }),
  )
  assert.equal(res.headers.get("set-cookie"), null)
  assert.equal(calls[0].url, "http://gw/v1/sessions")
  assert.equal((calls[0].init.headers as Record<string, string>).authorization, "Bearer rsk_x")
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), { agent_id: "crm", user: { id } })
})

test("over HTTPS the cookie works inside a cross-site iframe", async () => {
  const sandbox = createSandbox({ ...base, fetch: fakeGateway([]) })
  const res = await sandbox.startSession(new Request("https://app/api/assistant/session", { method: "POST" }))
  assert.match(res.headers.get("set-cookie")!, /SameSite=None; Secure; Partitioned/)
})

test("malformed cookies are ignored", () => {
  assert.equal(sandboxIdFrom(`${SANDBOX_COOKIE}=sandbox_short`), null)
  assert.equal(sandboxIdFrom(`${SANDBOX_COOKIE}=../../etc`), null)
  assert.equal(sandboxIdFrom(null), null)
})

test("one address can only start so many sessions", async () => {
  const sandbox = createSandbox({ ...base, sessionsPerWindow: 2, fetch: fakeGateway([]) })
  const start = () =>
    sandbox.startSession(new Request("http://app/x", { method: "POST", headers: { "x-forwarded-for": "9.9.9.9, 10.0.0.1" } }))
  assert.equal((await start()).status, 200)
  assert.equal((await start()).status, 200)
  assert.equal((await start()).status, 429)
})

test("reset forwards the visitor's sandbox to the tools service", async () => {
  const calls: Call[] = []
  const sandbox = createSandbox({ ...base, fetch: fakeGateway(calls) })
  const id = "sandbox_" + "b".repeat(32)
  const res = await sandbox.reset(new Request("http://app/api/sandbox/reset", { method: "POST", headers: { cookie: `${SANDBOX_COOKIE}=${id}` } }))
  assert.deepEqual(await res.json(), { reset: true })
  assert.equal(calls[0].url, "http://tools/sandbox/reset")
  assert.equal((calls[0].init.headers as Record<string, string>)["x-sandbox-id"], id)
})

test("gateway failures are reported without leaking details", async () => {
  const sandbox = createSandbox({ ...base, fetch: fakeGateway([], 500) })
  const res = await sandbox.startSession(new Request("http://app/x", { method: "POST" }))
  assert.equal(res.status, 502)
})
