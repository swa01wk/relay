import Link from "next/link"

import { Logo } from "@/components/vnb/logo"

/** Where the portal's many decorative links lead — just like the real thing. */
export default async function InfoPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const title = slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  return (
    <div className="mx-auto max-w-3xl bg-white p-6">
      <Logo size={36} />
      <h1 className="mt-4 text-[16px] font-bold text-[#6e1423]">{title}</h1>
      <div className="gv-msg-info mt-2">
        This facility is temporarily unavailable through Internet Banking. Please visit your home branch or call 1800 11 2244. Inconvenience caused is regretted.
      </div>
      <p className="mt-3">
        <Link href="/home">« Back to Internet Banking</Link> · <Link href="/">Home</Link>
      </p>
      <p className="gv-note mt-6">Vasundhara National Bank is a made-up bank in a Relay demo; this page stands in for the many sections such portals have.</p>
    </div>
  )
}
