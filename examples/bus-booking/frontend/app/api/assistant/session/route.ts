import { sandboxEnabled } from "@relay/example-sandbox"

import { sandbox, startTravellerSession } from "@/lib/session"

/** Start the assistant for the current traveller; the browser gets only the session id and token. */
export async function POST(request: Request) {
  return sandboxEnabled() ? sandbox.startSession(request) : startTravellerSession()
}
