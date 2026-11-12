import Link from "next/link"

import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-center">
      <h1 className="text-2xl font-semibold">We couldn&apos;t find that.</h1>
      <p className="text-muted-foreground">The bus or booking may not exist, or the date has passed.</p>
      <Button asChild>
        <Link href="/">Search buses</Link>
      </Button>
    </div>
  )
}
