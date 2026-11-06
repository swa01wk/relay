/**
 * Experience Center mode (NEXT_PUBLIC_RELAY_SANDBOX=1): each visitor gets their own copy of the
 * CRM data. Server-only — imported by the route handlers and the dashboard page.
 */
import { createSandbox } from "@relay/example-sandbox"

export { SANDBOX_COOKIE, sandboxEnabled, sandboxIdFrom } from "@relay/example-sandbox"

export const sandbox = createSandbox({
  // The gateway as this server reaches it (inside Docker: http://gateway:8080).
  gatewayUrl: process.env.RELAY_GATEWAY_URL ?? process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080",
  agentId: process.env.NEXT_PUBLIC_AGENT_ID ?? "sales-crm",
  projectId: process.env.NEXT_PUBLIC_PROJECT_ID ?? "proj-sales-crm",
  // Hosted gateway: the demo project's secret key. Without it, a local dev gateway is used.
  secretKey: process.env.RELAY_SECRET_KEY,
  toolsUrl: process.env.CRM_TOOLS_URL ?? "http://localhost:8091",
})
