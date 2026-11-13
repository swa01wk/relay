import { sandboxEnabled } from "@relay/example-sandbox"

import { sandbox } from "@/lib/session"

/** Experience Center: throw away this visitor's data (trips, wishlists, reviews). */
export async function POST(request: Request) {
  if (!sandboxEnabled()) return new Response("Not found", { status: 404 })
  return sandbox.reset(request)
}
