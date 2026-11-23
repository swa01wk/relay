import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"

import "./globals.css"
import { BankActions } from "@/components/bank/bank-actions"
import { SiteHeader } from "@/components/bank/site-header"
import { AssistantPanel } from "@/components/relay/assistant-panel"
import { RelayProvider } from "@/components/relay/relay-provider"
import { ResultsCanvas } from "@/components/relay/results-canvas"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { bank } from "@/lib/bank"
import type { MyContext } from "@/lib/types"

const sans = Geist({ subsets: ["latin"], variable: "--font-sans" })
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" })

export const metadata: Metadata = {
  title: "Kestrel Bank — net banking",
  description: "Example net banking site with a Relay voice and text banking assistant",
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  let me: MyContext | null = null
  let attention = 0
  try {
    const [ctx, items] = await Promise.all([bank<MyContext>("/api/me"), bank<{ total: number }>("/api/attention")])
    me = ctx
    attention = items.total
  } catch {
    me = null
  }
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} font-sans antialiased`}>
      <body>
        <TooltipProvider>
          <RelayProvider>
            <BankActions />
            <div className="flex min-h-svh">
              <div className="flex min-w-0 flex-1 flex-col">
                <SiteHeader customerName={me?.customer.name} attention={attention} />
                <ResultsCanvas />
                <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
                  {me ? (
                    children
                  ) : (
                    <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm">
                      <p className="font-medium">The bank API isn&apos;t reachable.</p>
                      <p className="mt-1 text-muted-foreground">
                        Start it (port 8095): <code>docker compose -f infra/docker/docker-compose.yml up -d bank-tools</code>, then reload.
                      </p>
                    </div>
                  )}
                </main>
                <footer className="border-t py-6 text-center text-xs text-muted-foreground">
                  Kestrel Bank is a demo — no real accounts, money or cards. Assistant powered by Relay.
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
