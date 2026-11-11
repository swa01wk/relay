/**
 * The Experience Center catalog. One entry per example app; the gallery, the sandbox page and
 * the home page's use-case section are all built from this list.
 *
 * `url` is where the example app runs in sandbox mode (NEXT_PUBLIC_RELAY_SANDBOX=1). Next.js
 * inlines NEXT_PUBLIC_* only when written out literally, so each example reads its own variable.
 */

export type Example = {
  slug: string
  name: string
  industry: string
  /** One line for cards. */
  tagline: string
  description: string
  url: string
  /** What to try — shown next to the sandbox; visitors copy them into the assistant. */
  prompts: string[]
  /** What the demo shows off. */
  highlights: string[]
  /** "voice" when the example supports speaking to it. */
  modes: ("voice" | "text")[]
}

export const examples: Example[] = [
  {
    slug: "storefront",
    name: "Oakline store",
    industry: "Ecommerce",
    tagline: "Shop by asking. Cart, checkout and returns by voice.",
    description:
      "An online store with a catalog, product pages, cart, checkout, orders and a wishlist. The assistant finds and compares products, filters the catalog, fills the checkout form from what you say, and proposes cart changes, orders, cancellations and returns for you to approve.",
    url: process.env.NEXT_PUBLIC_EXAMPLE_STOREFRONT_URL ?? "http://localhost:3004",
    prompts: [
      "Show me noise-cancelling headphones under $200",
      "Compare the Aurora Wireless Headphones and the Echo Buds Pro",
      "Add two Pulse Mini Speakers to my cart and apply WELCOME10",
      "Check out with express shipping to 500 Market St, San Francisco, CA 94105",
      "Where is my latest order? Can I still cancel it?",
      "Start a return for my Echo Buds — they arrived damaged",
    ],
    highlights: ["Catalog filters on screen", "Checkout form filled by voice", "Approved cart and order changes", "Per-shopper data"],
    modes: ["voice", "text"],
  },
  {
    slug: "sales-crm",
    name: "Sales CRM",
    industry: "Sales",
    tagline: "Ask your pipeline anything. Update deals by talking.",
    description:
      "A shadcn dashboard with accounts, contacts, deals and activities. The assistant searches and charts the data, navigates and filters the app, fills its forms, and proposes changes you approve.",
    url: process.env.NEXT_PUBLIC_EXAMPLE_SALES_CRM_URL ?? "http://localhost:3002/dashboard",
    prompts: [
      "Show me the pipeline by stage as a chart",
      "Which deals close this month and are still in Negotiation?",
      "Compare our top three reps this quarter",
      "Move the Northwind Logistics deal to Closed Won",
      "Log a call with Brightpath Health about the renewal",
    ],
    highlights: ["Charts & tables on a canvas", "Screen navigation and filters", "Form filling", "Approved writes"],
    modes: ["voice", "text"],
  },
  {
    slug: "mortgage-servicing",
    name: "Mortgage servicing",
    industry: "Financial services",
    tagline: "Rate corrections with a human in the loop.",
    description:
      "A servicing console for loan officers. The assistant looks up borrowers, explains payment history, drafts a rate correction and walks it through approve → commit → verify, so nothing changes without a person signing off.",
    url: process.env.NEXT_PUBLIC_EXAMPLE_MORTGAGE_URL ?? "http://localhost:3000",
    prompts: [
      "Find Rajesh Sharma and show his mortgage",
      "What did he pay over the last three months?",
      "Prepare a rate correction to 5.875% effective the first of next month",
      "Submit it for approval",
    ],
    highlights: ["Deterministic routes", "Approval before commit", "Verified writes", "Shared screen state"],
    modes: ["voice", "text"],
  },
]

export function exampleBySlug(slug: string): Example | undefined {
  return examples.find((e) => e.slug === slug)
}
