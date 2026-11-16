import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"

import "./globals.css"
import { AssistantPanel } from "@/components/relay/assistant-panel"
import { RelayProvider } from "@/components/relay/relay-provider"
import { ResultsCanvas } from "@/components/relay/results-canvas"
import { SiteHeader } from "@/components/shop/site-header"
import { StoreActions } from "@/components/shop/store-actions"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { shop } from "@/lib/shop"
import type { ShopperContext } from "@/lib/types"

const sans = Geist({ subsets: ["latin"], variable: "--font-sans" })
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" })

export const metadata: Metadata = {
  title: "Oakline — goods for home, desk and trail",
  description: "Example online store with a Relay voice and text shopping assistant",
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  let me: ShopperContext | null = null
  try {
    me = await shop<ShopperContext>("/api/me")
  } catch {
    me = null
  }
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} font-sans antialiased`}>
      <body>
        <TooltipProvider>
          <RelayProvider>
            <StoreActions />
            <div className="flex min-h-svh">
              <div className="flex min-w-0 flex-1 flex-col">
                <SiteHeader cartCount={me?.cart_items ?? 0} wishlistCount={me?.wishlist_items ?? 0} shopperName={me?.shopper.name} />
                <ResultsCanvas />
                <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
                  {me ? (
                    children
                  ) : (
                    <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm">
                      <p className="font-medium">The store API isn&apos;t reachable.</p>
                      <p className="mt-1 text-muted-foreground">
                        Start it (port 8092): <code>docker compose -f infra/docker/docker-compose.yml up -d shop-tools</code>, then reload.
                      </p>
                    </div>
                  )}
                </main>
                <footer className="border-t py-6 text-center text-xs text-muted-foreground">
                  Oakline is a demo store — no real orders, payments or deliveries. Assistant powered by Relay.
                </footer>
              </div>
              <AssistantPanel />
            </div>
            <Toaster position="bottom-left" />
          </RelayProvider>
        </TooltipProvider>
      </body>
    </html>
  )
}
