import { AppSidebar } from "@/components/app-sidebar"
import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { DealsTable } from "@/components/deals-table"
import { ApprovalDialog } from "@/components/relay/approval-dialog"
import { AssistantPanel } from "@/components/relay/assistant-panel"
import { RelayInsights } from "@/components/relay/relay-insights"
import { RelayProvider } from "@/components/relay/relay-provider"
import { SectionCards } from "@/components/section-cards"
import { SiteHeader } from "@/components/site-header"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { getDashboard, type Dashboard } from "@/lib/crm"

export default async function Page() {
  let dashboard: Dashboard | null = null
  try {
    dashboard = await getDashboard()
  } catch {
    dashboard = null
  }

  return (
    <RelayProvider>
      <SidebarProvider
        style={
          {
            "--sidebar-width": "calc(var(--spacing) * 72)",
            "--header-height": "calc(var(--spacing) * 12)",
          } as React.CSSProperties
        }
      >
        <AppSidebar variant="inset" />
        <SidebarInset>
          <SiteHeader title="Sales dashboard" asOf={dashboard?.as_of} />
          <div className="flex flex-1 flex-col">
            <div className="@container/main flex flex-1 flex-col gap-2">
              <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
                <RelayInsights />
                {dashboard ? (
                  <>
                    <SectionCards kpis={dashboard.kpis} />
                    <div className="px-4 lg:px-6">
                      <ChartAreaInteractive revenue={dashboard.revenue} />
                    </div>
                    <DealsTable deals={dashboard.deals} />
                  </>
                ) : (
                  <div className="px-4 lg:px-6">
                    <Alert variant="destructive">
                      <AlertTitle>CRM data unavailable</AlertTitle>
                      <AlertDescription>
                        Start the CRM tools API (port 8091) — e.g. docker compose -f
                        infra/docker/docker-compose.yml up -d crm-tools — and reload.
                      </AlertDescription>
                    </Alert>
                  </div>
                )}
              </div>
            </div>
          </div>
        </SidebarInset>
        <AssistantPanel />
        <ApprovalDialog />
      </SidebarProvider>
    </RelayProvider>
  )
}
