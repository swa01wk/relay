"use client"

import * as React from "react"

import { useRelayAction } from "@/components/relay/relay-provider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

/** Details / Reviews tabs on the product page, switchable by the assistant (SWITCH_PRODUCT_TAB). */
export function ProductTabs({ details, reviews, reviewCount }: { details: React.ReactNode; reviews: React.ReactNode; reviewCount: number }) {
  const [tab, setTab] = React.useState("details")
  useRelayAction(
    "SWITCH_PRODUCT_TAB",
    (params) => {
      const next = String(params.tab)
      if (next !== "details" && next !== "reviews") throw new Error("tab must be details or reviews")
      setTab(next)
      document.getElementById("product-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" })
      return { tab: next }
    },
    {
      description: "Switch the open product page to its details (features) or reviews tab.",
      parameters: { type: "object", properties: { tab: { type: "string", enum: ["details", "reviews"] } }, required: ["tab"] },
    },
  )
  return (
    <Tabs value={tab} onValueChange={setTab} id="product-tabs" className="scroll-mt-28">
      <TabsList>
        <TabsTrigger value="details">Details</TabsTrigger>
        <TabsTrigger value="reviews">Reviews ({reviewCount})</TabsTrigger>
      </TabsList>
      <TabsContent value="details" className="pt-4">
        {details}
      </TabsContent>
      <TabsContent value="reviews" className="pt-4">
        {reviews}
      </TabsContent>
    </Tabs>
  )
}
