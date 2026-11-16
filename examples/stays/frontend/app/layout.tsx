import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"

import "./globals.css"
import { AssistantPanel } from "@/components/relay/assistant-panel"
import { RelayProvider } from "@/components/relay/relay-provider"
import { ResultsCanvas } from "@/components/relay/results-canvas"
import { SiteHeader } from "@/components/stays/site-header"
import { StaysActions } from "@/components/stays/stays-actions"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { stays } from "@/lib/stays"
import type { MyContext } from "@/lib/types"

const sans = Geist({ subsets: ["latin"], variable: "--font-sans" })
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" })

export const metadata: Metadata = {
  title: "Roostly — homes for your next trip",
  description: "Example vacation rental site with a Relay voice and text trip assistant",
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  let me: MyContext | null = null
  try {
    me = await stays<MyContext>("/api/me")
  } catch {
    me = null
  }
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} font-sans antialiased`}>
      <body>
        <TooltipProvider>
          <RelayProvider>
            <StaysActions />
            <div className="flex min-h-svh">
              <div className="flex min-w-0 flex-1 flex-col">
                <SiteHeader upcoming={me?.upcoming_trips ?? 0} guestName={me?.guest.name} />
                <ResultsCanvas />
                <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
                  {me ? (
                    children
                  ) : (
                    <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm">
                      <p className="font-medium">The site API isn&apos;t reachable.</p>
                      <p className="mt-1 text-muted-foreground">
                        Start it (port 8094): <code>docker compose -f infra/docker/docker-compose.yml up -d stays-tools</code>, then reload.
                      </p>
                    </div>
                  )}
                </main>
                <footer className="border-t py-6 text-center text-xs text-muted-foreground">
                  Roostly is a demo rental site — no real homes, bookings or payments. Assistant powered by Relay.
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
