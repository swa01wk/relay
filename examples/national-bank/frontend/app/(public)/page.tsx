import Link from "next/link"

import { Logo } from "@/components/vnb/logo"
import { New } from "@/components/vnb/ui"

const info = (s: string) => `/info/${s.toLowerCase().replace(/[^a-z]+/g, "-")}`

// The quick-link farm under the login boxes. Only a few lead somewhere real.
const QUICK_LINKS: { label: string; href?: string; isNew?: boolean }[] = [
  { label: "Register Complaint of Unauthorised Transaction", href: "/complaints", isNew: true },
  { label: "Unlock VNB Authenticator" },
  { label: "QMS (e-Appointment)" },
  { label: "RBI Retail Direct portal" },
  { label: "Block ATM Card", href: "/services" },
  { label: "Open Savings / Current Account", href: "/open-account", isNew: true },
  { label: "Doorstep Banking" },
  { label: "VNB General Insurance Document Download" },
  { label: "VNB FASTag", href: "/bills" },
  { label: "VNB Salary Account", href: "/open-account" },
  { label: "NRI Services" },
  { label: "CYBER CRIME HELPLINE" },
  { label: "VNB Securities" },
  { label: "VNB Express Remit" },
  { label: "VNB Mutual Fund", href: "/mutual-funds" },
  { label: "VNB Life Insurance" },
]
const MORE_LINKS = [
  "Pension Seva", "Form 15G / 15H", "Interest Certificate", "Locate Branch / ATM", "Positive Pay System", "Senior Citizens Corner",
  "e-Auction of properties", "Tenders", "Holiday List", "Grievance Redressal", "Unclaimed Deposits", "Know Your IFSC", "Inoperative Accounts",
  "Gold Monetisation Scheme", "Sovereign Gold Bonds", "Kisan Credit Card", "Mudra Loans", "Stand-Up India", "PM SVANidhi", "Atal Pension Yojana",
]

function LoginPanel({ title, kind, corporate }: { title: string; kind: string; corporate?: boolean }) {
  return (
    <div className="flex-1 border border-[#cfcfcf] bg-[#fafafa] p-4">
      <div className="text-center">
        <div className="text-[13px] font-bold tracking-wide text-[#2f6b2f]">VNB NET-BANKING</div>
        <h2 className="mt-1 text-[20px] text-[#0a3d91]">
          <span className="text-[#6e1423]">{kind}</span> BANKING
        </h2>
        {corporate ? (
          <span className="mt-3 inline-block cursor-not-allowed bg-[#8a8a8a] px-6 py-2 text-[12px] font-bold text-white" title="Visit vnbbusiness portal">
            LOGIN »
          </span>
        ) : (
          <Link href="/login" className="mt-3 inline-block bg-[#6e1423] px-6 py-2 text-[12px] font-bold !text-white !no-underline hover:bg-[#8f1d30]">
            LOGIN »
          </Link>
        )}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
        {[`New ${corporate ? "Corporate" : "User"} Registration / Activation`, "How Do I", `Customer Care - ${title}`, "Lock & Unlock User"].map((label) => (
          <Link key={label} href={info(label)} className="border-l border-[#ddd] pl-2">
            {label}
          </Link>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-[#444]">
        {corporate
          ? "Corporate Banking application to administer and manage non personal accounts online."
          : "VNB's internet banking portal provides personal banking services that gives you complete control over all your banking demands online."}
      </p>
    </div>
  )
}

export default function Landing() {
  return (
    <div className="px-3 py-3">
      <div className="flex flex-col gap-3 md:flex-row">
        <LoginPanel title="Personal" kind="PERSONAL" />
        <LoginPanel title="Corporate" kind="CORPORATE" corporate />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 px-2 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
        {QUICK_LINKS.map((l) => (
          <Link key={l.label} href={l.href ?? info(l.label)}>
            › {l.label}
            {l.isNew && <New />}
          </Link>
        ))}
      </div>
      <details className="mt-2 text-center">
        <summary className="inline-block cursor-pointer border border-[#0a7a8a] px-4 py-1.5 text-[12px] text-[#0a3d91]">▼ More Useful Links</summary>
        <div className="mt-2 grid grid-cols-2 gap-1 text-left text-[11px] sm:grid-cols-4">
          {MORE_LINKS.map((label) => (
            <Link key={label} href={info(label)} data-relay-ignore>
              › {label}
            </Link>
          ))}
        </div>
      </details>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <div className="bg-gradient-to-br from-[#6e1423] to-[#a8324a] p-4 text-white">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#ffd76a]">Term deposit special</div>
          <div className="mt-1 text-[26px] font-bold leading-tight" style={{ fontFamily: "Georgia, serif" }}>
            Vasundhara Utsav
            <br />
            444 days @ 7.25%*
          </div>
          <div className="mt-1 text-[11px]">*Senior citizens 7.75% p.a. T&C apply. Valid till 31.03.2027.</div>
          <Link href="/deposits" className="mt-2 inline-block bg-[#e39b2d] px-3 py-1 text-[11px] font-bold !text-black !no-underline">
            Book now ›
          </Link>
        </div>
        <div className="bg-gradient-to-br from-[#1d4e2c] to-[#2f6b2f] p-4 text-white">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#ffd76a]">Retail loans</div>
          <div className="mt-1 text-[22px] font-bold leading-tight" style={{ fontFamily: "Georgia, serif" }}>
            Home · Car · Personal · Education · Gold · Against FD
          </div>
          <div className="mt-1 text-[11px]">Home loans from 8.50%* p.a. Concessions for women borrowers. *Linked to CIBIL score.</div>
          <Link href="/loans" className="mt-2 inline-block bg-[#e39b2d] px-3 py-1 text-[11px] font-bold !text-black !no-underline">
            Know more ›
          </Link>
        </div>
        <div className="border border-[#d9b46a] bg-[#fff8e1] p-4">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#a10000]">Jan Suraksha</div>
          <div className="mt-1 text-[18px] font-bold leading-tight text-[#6e1423]" style={{ fontFamily: "Georgia, serif" }}>
            PMJJBY ₹436 · PMSBY ₹20 · APY · Sukanya Samriddhi · PPF
          </div>
          <div className="mt-1 text-[11px]">Enrol online through Internet Banking › Government Schemes.</div>
          <Link href="/schemes" className="mt-2 inline-block text-[11px] font-bold">
            Enrol now ›
          </Link>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3 border border-[#cfcfcf] bg-[#fafafa] p-3 text-[11px]">
        <Logo size={30} withName={false} />
        <p>
          <b>Can&apos;t find what you need?</b> Ask <b>VNB Sahayak</b> (right) in English or Hindi — by voice or chat. It reads your accounts, explains charges and
          narrations, compares loans and deposits for you, and fills the forms; you approve anything it does.
        </p>
      </div>
    </div>
  )
}
