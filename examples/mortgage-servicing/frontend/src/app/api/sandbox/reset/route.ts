import { sandbox, sandboxEnabled } from "@/lib/sandbox";

/** Experience Center: throw away this visitor's changes. */
export async function POST(request: Request) {
  if (!sandboxEnabled()) return new Response("Not found", { status: 404 });
  return sandbox.reset(request);
}
