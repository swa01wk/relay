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

/** Screenshot of the example's home page (public/examples/<slug>.webp, 1200×750). */
export function screenshotOf(example: Example): string {
  return `/examples/${example.slug}.webp`
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
    slug: "bus-booking",
    name: "Wayline bus tickets",
    industry: "Travel",
    tagline: "Find the bus, pick the berth, book — by talking.",
    description:
      "An intercity bus booking site with search, filters, a fare calendar, a two-deck seat map, boarding points, passenger details and a trips page. The assistant searches and filters buses, selects seats and boarding points on the seat map, fills passenger details from your saved travellers, and proposes bookings, cancellations and reschedules for you to approve.",
    url: process.env.NEXT_PUBLIC_EXAMPLE_BUS_BOOKING_URL ?? "http://localhost:3005",
    prompts: [
      "AC sleeper buses from Bangalore to Hyderabad tomorrow night",
      "Which day next week is cheapest to Chennai?",
      "Open the cheapest one and pick two lower berths together, boarding at Silk Board",
      "Fill in me and Rahul as passengers and use WAYLINE10",
      "When does my next bus leave, and from where?",
      "What would it cost to cancel my Mysuru trip? Then move it to next Friday instead",
    ],
    highlights: ["Seat map driven by voice", "Search filters on screen", "Passenger form filled from saved travellers", "Approved bookings and cancellations"],
    modes: ["voice", "text"],
  },
  {
    slug: "stays",
    name: "Roostly stays",
    industry: "Hospitality",
    tagline: "Find the place, check the dates, book — by asking.",
    description:
      "A vacation rental site with search by place, dates and guests, listing pages with an availability calendar and full price breakdown, instant book or request-to-book, trips with host messages, and wishlists. The assistant searches and filters homes, sets dates and guests on the booking panel, fills Confirm and pay, and proposes bookings, changes, cancellations and reviews for you to approve.",
    url: process.env.NEXT_PUBLIC_EXAMPLE_STAYS_URL ?? "http://localhost:3006",
    prompts: [
      "A villa with a pool in Goa for 6 people, 20 to 23 December",
      "Cosy cottages in the hills that allow dogs, under ₹7,000 a night",
      "Compare the two Udaipur places on the lake",
      "Book the Anjuna studio for two next weekend and tell the host we arrive around 4",
      "When is my next trip, and how do I check in?",
      "What would I get back if I cancel my Ooty trip?",
    ],
    highlights: ["Booking panel driven by voice", "Price breakdown with fees and GST", "Instant book or host requests", "Approved bookings, changes and reviews"],
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
