/**
 * Starts the assistant's Relay session on the server, for the current guest, so the rental
 * tools receive that guest as X-Relay-User. Server-side only.
 *
 * - Experience Center (NEXT_PUBLIC_RELAY_SANDBOX=1): the visitor's sandbox is the guest.
 * - Otherwise: the demo guest. With RELAY_SECRET_KEY (hosted gateway) through /v1/sessions,
 *   without it through a local dev gateway's /dev/sessions.
 */
import { createSandbox } from "@relay/example-sandbox"
import { DEMO_GUEST_ID } from "@/lib/guest"

const GATEWAY = (process.env.RELAY_GATEWAY_URL ?? process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080").replace(/\/$/, "")
const AGENT_ID = process.env.NEXT_PUBLIC_AGENT_ID ?? "stays"
const PROJECT_ID = process.env.NEXT_PUBLIC_PROJECT_ID ?? "proj-stays"
const SECRET_KEY = process.env.RELAY_SECRET_KEY

export const sandbox = createSandbox({
  gatewayUrl: GATEWAY,
  agentId: AGENT_ID,
  projectId: PROJECT_ID,
  secretKey: SECRET_KEY,
  toolsUrl: process.env.STAYS_API_URL ?? "http://localhost:8094",
})

export async function startGuestSession(): Promise<Response> {
  const user = { id: DEMO_GUEST_ID }
  const res = SECRET_KEY
    ? await fetch(`${GATEWAY}/v1/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${SECRET_KEY}` },
        body: JSON.stringify({ agent_id: AGENT_ID, user }),
      })
    : await fetch(`${GATEWAY}/dev/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ project_id: PROJECT_ID, agent_id: AGENT_ID, user }),
      }).catch(() => null)
  if (!res || !res.ok) return Response.json({ error: `The Relay gateway at ${GATEWAY} is not reachable` }, { status: 502 })
  const body = (await res.json()) as { session_id: string; token: string }
  return Response.json({ sessionId: body.session_id, token: body.token })
}
