/**
 * Who is travelling — server-side only. This demo site has no sign-in page: everyone is the demo
 * traveller, except in the Experience Center, where each visitor is their own sandbox (cookie set by
 * proxy.ts). A real site would read its own login session here.
 */
import { cookies } from "next/headers"
import { SANDBOX_COOKIE, sandboxEnabled, sandboxIdFrom } from "@relay/example-sandbox"

export const DEMO_TRAVELLER_ID = process.env.BUS_DEMO_TRAVELLER_ID ?? "traveller-demo"

export async function currentTravellerId(): Promise<string> {
  if (!sandboxEnabled()) return DEMO_TRAVELLER_ID
  const id = sandboxIdFrom((await cookies()).get(SANDBOX_COOKIE)?.value)
  if (!id) throw new Error("no sandbox cookie (proxy.ts sets it)")
  return id
}
