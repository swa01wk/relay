import type { Metadata } from "next"

import "./globals.css"
import { BankActions } from "@/components/vnb/bank-actions"
import { AssistantPanel } from "@/components/relay/assistant-panel"
import { RelayProvider } from "@/components/relay/relay-provider"
import { ResultsCanvas } from "@/components/relay/results-canvas"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

export const metadata: Metadata = {
  title: "Vasundhara National Bank — Internet Banking",
  description: "Example public-sector bank portal with a Relay voice and text banking assistant",
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="antialiased">
      <body className="font-sans">
        <TooltipProvider>
          <RelayProvider>
            <BankActions />
            <div className="flex min-h-svh">
              <div className="flex min-w-0 flex-1 flex-col">
                <ResultsCanvas />
                <div className="gv flex-1">{children}</div>
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
