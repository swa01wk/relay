import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"

import "./globals.css"
import { AssistantPanel } from "@/components/relay/assistant-panel"
import { RelayProvider } from "@/components/relay/relay-provider"
import { ResultsCanvas } from "@/components/relay/results-canvas"
import { BusActions } from "@/components/bus/bus-actions"
import { SiteHeader } from "@/components/bus/site-header"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { bus } from "@/lib/bus"
import type { MyContext } from "@/lib/types"

const sans = Geist({ subsets: ["latin"], variable: "--font-sans" })
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" })

export const metadata: Metadata = {
  title: "Wayline — intercity bus tickets",
  description: "Example bus booking site with a Relay voice and text travel assistant",
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  let me: MyContext | null = null
  try {
    me = await bus<MyContext>("/api/me")
  } catch {
    me = null
  }
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} font-sans antialiased`}>
      <body>
        <TooltipProvider>
          <RelayProvider>
            <BusActions />
            <div className="flex min-h-svh">
              <div className="flex min-w-0 flex-1 flex-col">
                <SiteHeader upcoming={me?.upcoming_trips ?? 0} travellerName={me?.traveller.name} />
                <ResultsCanvas />
                <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
                  {me ? (
                    children
                  ) : (
                    <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm">
                      <p className="font-medium">The booking API isn&apos;t reachable.</p>
                      <p className="mt-1 text-muted-foreground">
                        Start it (port 8093): <code>docker compose -f infra/docker/docker-compose.yml up -d bus-tools</code>, then reload.
                      </p>
                    </div>
                  )}
                </main>
                <footer className="border-t py-6 text-center text-xs text-muted-foreground">
                  Wayline is a demo booking site — no real buses, tickets or payments. Assistant powered by Relay.
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
