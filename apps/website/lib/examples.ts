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
    slug: "banking",
    name: "Kestrel Bank",
    industry: "Banking",
    tagline: "Your bank, by asking. Spending, transfers and cards by voice.",
    description:
      "A net banking site with accounts, a searchable statement, transfers and payees, bills with autopay, debit and credit cards, fixed deposits and spending insights. The assistant explains where the money went, filters the statement and charts spending, fills the transfer form, and proposes payments, card locks, deposits and disputes for you to approve.",
    url: process.env.NEXT_PUBLIC_EXAMPLE_BANKING_URL ?? "http://localhost:3007",
    prompts: [
      "How much did I spend on food last month, and where?",
      "Show my Zomato orders this month — was I charged twice?",
      "Send ₹1,500 to Rohan for dinner",
      "Pay my electricity bill and turn on autopay for broadband",
      "Freeze my debit card and switch off international payments on the credit card",
      "What would ₹1 lakh in an FD for 15 months earn? Open it",
    ],
    highlights: ["Statement filtered on screen", "Spending charts", "Transfer form filled by voice", "Approved payments, card and FD changes"],
    modes: ["voice", "text"],
  },
  {
    slug: "national-bank",
    name: "National Bank",
    industry: "Public-sector banking",
    tagline: "A government-style bank portal, made usable by asking.",
    description:
      "A deliberately crowded public-sector net banking portal: cryptic passbook narrations, long rate tables, forms full of fine print. The assistant works out what is best for the customer — which loan for a need (it spots that a loan against their FD beats a personal loan), where to save, which government schemes they qualify for — explains charges, fills the portal's forms and proposes transfers, deposits, re-KYC and service requests for approval.",
    url: process.env.NEXT_PUBLIC_EXAMPLE_NATIONAL_BANK_URL ?? "http://localhost:3008",
    prompts: [
      "I need ₹2 lakh for my mother's surgery — which loan is best for me?",
      "What is this ₹590 'DECLINED TXN CHGS' in my statement?",
      "Where should I save ₹5,000 a month for 10 years? I have a 9-year-old daughter",
      "Should I prepay my car loan or open another FD?",
      "My KYC is overdue — sort it out",
      "Send ₹14,000 rent to my house owner and order a cheque book",
    ],
    highlights: ["Loan and savings advice from the customer's own numbers", "Narrations and charges explained", "Portal forms filled by voice", "Approved transfers, deposits and requests"],
    modes: ["voice", "text"],
  },
]

export function exampleBySlug(slug: string): Example | undefined {
  return examples.find((e) => e.slug === slug)
}
