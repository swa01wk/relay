"use client"

import * as React from "react"
import {
  BriefcaseBusinessIcon,
  Building2Icon,
  ChartColumnIcon,
  CircleHelpIcon,
  FileChartColumnIcon,
  LayoutDashboardIcon,
  Settings2Icon,
  TargetIcon,
  TriangleAlertIcon,
  UsersIcon,
  ZapIcon,
} from "lucide-react"

import { NavDocuments } from "@/components/nav-documents"
import { NavMain } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

const data = {
  user: { name: "Jordan Reyes", email: "jordan.reyes@example.com", avatar: "" },
  navMain: [
    { title: "Dashboard", url: "/dashboard", icon: <LayoutDashboardIcon /> },
    { title: "Deals", url: "#", icon: <BriefcaseBusinessIcon /> },
    { title: "Accounts", url: "#", icon: <Building2Icon /> },
    { title: "Reports", url: "#", icon: <ChartColumnIcon /> },
    { title: "Team", url: "#", icon: <UsersIcon /> },
  ],
  views: [
    { name: "Q4 forecast", url: "#", icon: <TargetIcon /> },
    { name: "At-risk deals", url: "#", icon: <TriangleAlertIcon /> },
    { name: "Win/loss review", url: "#", icon: <FileChartColumnIcon /> },
  ],
  navSecondary: [
    { title: "Settings", url: "#", icon: <Settings2Icon /> },
    { title: "Get Help", url: "#", icon: <CircleHelpIcon /> },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="data-[slot=sidebar-menu-button]:p-1.5!">
              <a href="/dashboard">
                <ZapIcon className="size-5!" />
                <span className="text-base font-semibold">Relay CRM</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavDocuments items={data.views} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
