/**
 * Experience Center mode (NEXT_PUBLIC_RELAY_SANDBOX=1): each visitor gets their own copy of the
 * mortgage data. Server-only — imported by the route handlers.
 */
import { createSandbox } from "@relay/example-sandbox";

export { sandboxEnabled } from "@relay/example-sandbox";

export const sandbox = createSandbox({
  // The gateway as this server reaches it (inside Docker: http://gateway:8080).
  gatewayUrl: process.env.RELAY_GATEWAY_URL ?? process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080",
  agentId: process.env.NEXT_PUBLIC_AGENT_ID ?? "agent-mortgage-ref",
  projectId: process.env.NEXT_PUBLIC_PROJECT_ID ?? "proj-mortgage-poc",
  // Hosted gateway: the demo project's secret key. Without it, a local dev gateway is used.
  secretKey: process.env.RELAY_SECRET_KEY,
  toolsUrl: process.env.MORTGAGE_TOOLS_URL ?? "http://localhost:8090",
});
