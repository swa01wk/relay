"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"

const TABS = [
  { href: "/home", label: "My Accounts & Profile" },
  { href: "/transfers", label: "Payments / Transfers" },
  { href: "/bills", label: "Bill Payments" },
  { href: "/services", label: "e-Services" },
  { href: "/deposits", label: "Deposits" },
  { href: "/loans", label: "Loans" },
  { href: "/mutual-funds", label: "Mutual Funds" },
  { href: "/schemes", label: "Government Schemes" },
  { href: "/tax", label: "e-Tax" },
  { href: "/open-account", label: "Open Account" },
  { href: "/complaints", label: "Requests & Enquiries" },
  { href: "/info/demat-ipo", label: "Demat / IPO" },
]

type MenuItem = { href: string; label: string }
const MENU: { title: string; items: MenuItem[] }[] = [
  {
    title: "My Accounts & Profile",
    items: [
      { href: "/home", label: "Account Summary" },
      { href: "/statement", label: "Account Statement / Download" },
      { href: "/profile", label: "Profile / KYC" },
      { href: "/profile#nominees", label: "Nomination" },
      { href: "/change-password", label: "Change Password" },
    ],
  },
  {
    title: "Payments / Transfers",
    items: [
      { href: "/transfers", label: "Funds Transfer (Within VNB / Other Bank)" },
      { href: "/transfers#own-transfer", label: "Own Account Transfer" },
      { href: "/transfers#manage-beneficiary", label: "Manage Beneficiary" },
      { href: "/transfers#transfer-limit", label: "Set Transaction Limit" },
      { href: "/standing-instructions", label: "Standing Instructions" },
      { href: "/info/upi-settings", label: "UPI Settings" },
    ],
  },
  {
    title: "Bill Payments",
    items: [
      { href: "/bills", label: "Pay Bills / Recharge" },
      { href: "/bills#autopay", label: "Auto Pay" },
      { href: "/bills#add-biller", label: "Register Biller" },
    ],
  },
  {
    title: "e-Services",
    items: [
      { href: "/open-account", label: "Open New Account (SB / Current / Minor)" },
      { href: "/services#cheque-book", label: "Cheque Book Request" },
      { href: "/services#stop-cheque", label: "Stop Cheque Payment" },
      { href: "/services#positive-pay", label: "Positive Pay System" },
      { href: "/services#cheque-status", label: "Cheque Status Enquiry" },
      { href: "/services#debit-card", label: "ATM / Debit Card Services" },
      { href: "/services#re-kyc", label: "Re-KYC Self Declaration" },
      { href: "/services#interest-certificate", label: "Interest / TDS Certificate" },
      { href: "/locker", label: "Safe Deposit Locker" },
      { href: "/services#requests", label: "Service Request Status" },
    ],
  },
  {
    title: "Deposits",
    items: [
      { href: "/deposits", label: "Interest Rates & My Deposits" },
      { href: "/deposits#open-fd", label: "e-TDR / e-STDR (Fixed Deposit)" },
      { href: "/deposits#open-rd", label: "e-RD (Recurring Deposit)" },
      { href: "/deposits#close-fd", label: "Close Deposit Prematurely" },
    ],
  },
  {
    title: "Loans",
    items: [
      { href: "/loans", label: "Loan Products & Interest Rates" },
      { href: "/loans#my-loans", label: "My Loan Accounts" },
      { href: "/loans#emi-calculator", label: "EMI Calculator" },
      { href: "/loans#apply", label: "Apply for Loan" },
      { href: "/loans#prepay", label: "Loan Prepayment" },
    ],
  },
  {
    title: "Investments",
    items: [
      { href: "/mutual-funds", label: "Mutual Funds (Lumpsum / SIP)" },
      { href: "/nps", label: "National Pension System (NPS)" },
      { href: "/schemes#ppf", label: "PPF Deposit" },
      { href: "/info/sovereign-gold-bonds", label: "Sovereign Gold Bonds" },
    ],
  },
  {
    title: "Government Schemes",
    items: [
      { href: "/schemes", label: "PMJJBY / PMSBY / APY" },
      { href: "/schemes#ssy", label: "Sukanya Samriddhi Yojana" },
    ],
  },
  {
    title: "e-Tax",
    items: [
      { href: "/tax", label: "Pay Income Tax (Challan 280)" },
      { href: "/tax#form-15g", label: "Form 15G / 15H" },
      { href: "/services#interest-certificate", label: "Interest Certificate" },
    ],
  },
  {
    title: "Requests & Enquiries",
    items: [
      { href: "/complaints", label: "Lodge Complaint / Track Status" },
      { href: "/services#requests", label: "Service Request Status" },
    ],
  },
]

const active = (pathname: string, href: string) => href.split("#")[0] === pathname

export function TopTabs() {
  const pathname = usePathname()
  return (
    <nav className="gv-tabs flex overflow-x-auto bg-[#6e1423] text-[11.5px]" aria-label="Sections">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} aria-current={active(pathname, t.href) ? "page" : undefined} data-relay-ignore={t.href.startsWith("/info") || undefined}>
          {t.label}
        </Link>
      ))}
    </nav>
  )
}

export function LeftMenu() {
  const pathname = usePathname()
  return (
    <nav className="gv-menu border border-[#c9c2a8] bg-white" aria-label="Menu">
      <div className="bg-[#2f6b2f] px-2 py-1 text-[11px] font-bold text-white">Quick Links</div>
      {MENU.map((group) => (
        <details key={group.title} open={group.items.some((i) => active(pathname, i.href))}>
          <summary>{group.title}</summary>
          <ul>
            {group.items.map((i) => (
              <li key={i.href}>
                <Link href={i.href} aria-current={active(pathname, i.href) && !i.href.includes("#") ? "page" : undefined}>
                  {i.label}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </nav>
  )
}

/** "Your session will expire in 04:59" — resets on activity, like the real thing (but never logs out). */
export function SessionTimer() {
  const [left, setLeft] = React.useState(300)
  React.useEffect(() => {
    const tick = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000)
    const reset = () => setLeft(300)
    window.addEventListener("keydown", reset)
    window.addEventListener("click", reset)
    return () => {
      clearInterval(tick)
      window.removeEventListener("keydown", reset)
      window.removeEventListener("click", reset)
    }
  }, [])
  const mm = String(Math.floor(left / 60)).padStart(2, "0")
  const ss = String(left % 60).padStart(2, "0")
  return (
    <span className={left < 60 ? "font-bold text-[#c00]" : ""}>
      Session expires in {mm}:{ss}
    </span>
  )
}
