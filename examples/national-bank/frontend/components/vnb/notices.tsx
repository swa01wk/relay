import Link from "next/link"

const SCROLLER = [
  "VNB never asks for your PIN, OTP, CVV or password over phone, SMS or e-mail. Any such call is from a fraudster.",
  "Re-KYC: customers whose KYC is due can submit a self-declaration through Internet Banking › e-Services › Re-KYC.",
  "Utsav 444 days term deposit at 7.25% p.a. (senior citizens 7.75%) — valid till 31.03.2027.",
  "Enrol in PMJJBY (₹436 p.a.) and PMSBY (₹20 p.a.) through Internet Banking › Government Schemes.",
  "Sukanya Samriddhi Yojana can be opened for a girl child below 10 years of age. Interest 8.2% p.a.",
  "Internet Banking will not be available on Sunday from 00:30 to 02:30 hrs due to scheduled maintenance.",
]

/** The scrolling notice strip every page of the portal has. */
export function Marquee() {
  return (
    <div className="gv-marquee border-y border-[#d9b46a] bg-[#fff8e1] py-1 text-[11px] font-bold text-[#a10000]" role="note" aria-label="Notices">
      <span>{SCROLLER.join("    ✦    ")}</span>
    </div>
  )
}

/** The two red warning lines on top of every page. */
export function FraudBanner() {
  return (
    <div className="border border-[#cfcfcf] bg-white px-2 py-1 text-center text-[11px] font-bold leading-5 text-[#0a3d91]">
      If slowness is observed during page loading, please refresh the page for better experience.
      <br />
      <span className="text-[#a10000]">VNB never asks for confidential information such as PIN and OTP from customers. Any such call can be made only by a fraudster. Please do not share personal info.</span>
    </div>
  )
}

const FOOTER_LINKS = [
  "About Us", "Disclaimer", "Privacy Statement", "Terms of Service (Terms & Conditions)", "Hyperlink Policy", "Security Tips",
  "Grievance Redressal Policy", "Customer Rights Policy", "Citizen's Charter", "Unclaimed Deposits (UDGAM)", "Right to Information (RTI)",
  "Banking Ombudsman Scheme", "Interest Rates on Deposits", "Service Charges", "Branch / ATM Locator", "Sitemap", "Contact Us", "Careers",
]

/** The link-farm footer. Decorative links go to /info/… (not pages the assistant sends anyone to). */
export function Footer() {
  return (
    <footer className="mt-3 border-t-4 border-[#6e1423] bg-[#2b2b2b] px-3 py-3 text-[11px] text-[#ddd]">
      <div className="flex flex-wrap gap-x-1 gap-y-1">
        {FOOTER_LINKS.map((label, i) => (
          <span key={label}>
            <Link href={`/info/${label.toLowerCase().replace(/[^a-z]+/g, "-")}`} className="!text-[#ddd]" data-relay-ignore>
              {label}
            </Link>
            {i < FOOTER_LINKS.length - 1 && <span className="px-1 text-[#888]">|</span>}
          </span>
        ))}
      </div>
      <p className="mt-2 text-[#aaa]">
        © National Bank. Site best viewed in Internet Explorer 11 / Chrome at 1024 × 768 resolution. Toll free: 1800 11 2244 · 1800 425 8899 (24×7).
      </p>
      <p className="mt-1 text-[#aaa]">
        National Bank is a made-up bank for a Relay demo — no real accounts, money or schemes. Rates and rules are illustrative.
      </p>
    </footer>
  )
}
