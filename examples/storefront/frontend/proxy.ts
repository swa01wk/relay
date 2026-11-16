import { NextResponse, type NextRequest } from "next/server"
import { newSandboxId, SANDBOX_COOKIE, sandboxCookie, sandboxEnabled, sandboxIdFrom } from "@relay/example-sandbox"

/**
 * Experience Center: give each new visitor a sandbox (their own copy of the store) before the first
 * page renders, so server components already know whose cart to show.
 */
export function proxy(request: NextRequest) {
  if (!sandboxEnabled() || sandboxIdFrom(request.cookies.get(SANDBOX_COOKIE)?.value)) return NextResponse.next()
  const id = newSandboxId()
  request.cookies.set(SANDBOX_COOKIE, id) // visible to this request's render
  const response = NextResponse.next({ request: { headers: request.headers } })
  response.headers.append("set-cookie", sandboxCookie(id, request))
  return response
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
}
