import Link from "next/link"

import { AssistantButton } from "@/components/vnb/assistant-button"
import { Logo } from "@/components/vnb/logo"
import { FraudBanner, Footer, Marquee } from "@/components/vnb/notices"

const NAV: { label: string; items: string[]; isNew?: boolean }[] = [
  { label: "Services", items: ["Personal Banking", "NRI Services", "Agricultural Banking", "SME Banking", "Pension Disbursement", "Locker Facility"] },
  { label: "FAQ", items: ["Internet Banking FAQ", "Mobile Banking FAQ", "Card FAQ", "Loans FAQ"] },
  { label: "Corporate Website", items: [] },
  { label: "VNB Pay Lite (VNBMOPS)", items: ["Pay fees", "Pay taxes", "Pay utility bills"] },
  { label: "Donations", items: [] },
  { label: "VNB Collect", items: [] },
  { label: "Videos", items: [] },
  { label: "Apply for SB / Current Account", items: ["Savings Account", "Current Account", "Basic Savings (BSBD)"], isNew: true },
  { label: "NPS", items: ["Open NPS", "Contribute"] },
  { label: "VNB Unipay", items: [] },
  { label: "VNB Loans", items: ["Home Loan", "Car Loan", "Personal Loan", "Education Loan", "Gold Loan"], isNew: true },
  { label: "Update KYC", items: ["Update KYC"], isNew: true },
]

// Menu entries that lead to a real page of the portal (the rest are "visit your branch" pages).
const PAGES: Record<string, string> = {
  "Savings Account": "/open-account",
  "Current Account": "/open-account",
  "Basic Savings (BSBD)": "/open-account",
  "Locker Facility": "/locker",
  "Pay utility bills": "/bills",
  "Pay taxes": "/tax",
  "Open NPS": "/nps",
  Contribute: "/nps",
  "Update KYC": "/services#re-kyc",
}

const slug = (s: string) => `/info/${s.toLowerCase().replace(/[^a-z]+/g, "-")}`

/** The public site: the overcrowded menu bar, notices and the link farm. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[1400px] bg-white">
      <header className="flex flex-wrap items-center justify-between gap-3 px-4 py-2">
        <Link href="/" className="!no-underline">
          <Logo />
        </Link>
        <div className="flex items-center gap-3 text-[11px]">
          <a href="#main">Skip to main content</a>
          <span className="rounded bg-[#e39b2d] px-2 py-1 font-bold text-[#3b1d00]">A A A</span>
          <AssistantButton />
        </div>
      </header>
      <nav className="flex flex-wrap bg-[#6e1423] text-[12px]" aria-label="Main menu">
        {NAV.map((item) => (
          <details key={item.label} className="group relative border-r border-white/20">
            <summary className="cursor-pointer list-none px-2.5 py-2 text-white hover:bg-[#e39b2d] hover:text-black">
              {item.label}
              {item.isNew && <sup className="text-[9px] text-[#ffd76a]"> New</sup>}
              {item.items.length > 0 && " ▾"}
            </summary>
            {item.items.length > 0 && (
              <ul className="absolute left-0 z-20 min-w-48 border border-[#999] bg-white py-1 shadow">
                {item.items.map((sub) => (
                  <li key={sub}>
                    <Link href={PAGES[sub] ?? (sub.includes("Loan") ? "/loans" : slug(sub))} className="block px-3 py-1 !no-underline hover:bg-[#fff3d6]">
                      {sub}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </details>
        ))}
        <span className="ml-auto bg-[#2f6b2f] px-3 py-2 font-bold text-white">हिंदी</span>
      </nav>
      <FraudBanner />
      <Marquee />
      <main id="main">{children}</main>
      <Footer />
    </div>
  )
}
