import Link from "next/link"

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl bg-white p-6">
      <h1 className="text-[16px] font-bold text-[#6e1423]">Page not found</h1>
      <div className="gv-msg-err mt-2">The page you requested could not be found. Your session may have expired.</div>
      <p className="mt-3">
        <Link href="/home">Go to Account Summary</Link> · <Link href="/">Home</Link>
      </p>
    </div>
  )
}
