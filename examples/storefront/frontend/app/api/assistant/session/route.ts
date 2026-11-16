import { sandboxEnabled } from "@relay/example-sandbox"

import { sandbox, startShopperSession } from "@/lib/session"

/** Start the assistant for the current shopper; the browser gets only the session id and token. */
export async function POST(request: Request) {
  return sandboxEnabled() ? sandbox.startSession(request) : startShopperSession()
}
