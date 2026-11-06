import { sandbox, sandboxEnabled } from "@/lib/sandbox"

/** Experience Center: start a Relay session for this visitor's sandbox (see lib/sandbox.ts). */
export async function POST(request: Request) {
  if (!sandboxEnabled()) return new Response("Not found", { status: 404 })
  return sandbox.startSession(request)
}
