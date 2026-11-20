/**
 * Who the customer is — server-side only. This demo bank has no sign-in page: everyone is the demo
 * customer, except in the Experience Center, where each visitor is their own sandbox (cookie set by
 * proxy.ts). A real bank would read its own login session here.
 */
import { cookies } from "next/headers"
import { SANDBOX_COOKIE, sandboxEnabled, sandboxIdFrom } from "@relay/example-sandbox"

export const DEMO_CUSTOMER_ID = process.env.BANK_DEMO_CUSTOMER_ID ?? "customer-demo"

export async function currentCustomerId(): Promise<string> {
  if (!sandboxEnabled()) return DEMO_CUSTOMER_ID
  const id = sandboxIdFrom((await cookies()).get(SANDBOX_COOKIE)?.value)
  if (!id) throw new Error("no sandbox cookie (proxy.ts sets it)")
  return id
}
