/**
 * Who is shopping — server-side only. This demo store has no sign-in page: everyone is the demo
 * shopper, except in the Experience Center, where each visitor is their own sandbox (cookie set by
 * proxy.ts). A real store would read its own login session here.
 */
import { cookies } from "next/headers"
import { SANDBOX_COOKIE, sandboxEnabled, sandboxIdFrom } from "@relay/example-sandbox"

export const DEMO_SHOPPER_ID = process.env.SHOP_DEMO_SHOPPER_ID ?? "shopper-demo"

export async function currentShopperId(): Promise<string> {
  if (!sandboxEnabled()) return DEMO_SHOPPER_ID
  const id = sandboxIdFrom((await cookies()).get(SANDBOX_COOKIE)?.value)
  if (!id) throw new Error("no sandbox cookie (proxy.ts sets it)")
  return id
}
