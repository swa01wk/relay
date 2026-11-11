import Link from "next/link"
import { HeartIcon, PackageIcon, SearchIcon, ShoppingCartIcon } from "lucide-react"

import { AssistantToggle, ResetDemoButton } from "@/components/shop/header-controls"
import { Button } from "@/components/ui/button"
import { CATEGORIES } from "@/lib/types"

export function SiteHeader({ cartCount, wishlistCount, shopperName }: { cartCount: number; wishlistCount: number; shopperName?: string }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 lg:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight" aria-label="Oakline home">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
              <path d="M12 3c4 3 6 6.5 6 10a6 6 0 0 1-12 0c0-3.5 2-7 6-10Z" fill="currentColor" />
              <path d="M12 9v12" stroke="var(--primary)" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </span>
          <span className="hidden sm:inline">Oakline</span>
        </Link>
        <form action="/products" className="relative ml-2 hidden max-w-sm flex-1 md:block" role="search" data-relay-ignore>
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            name="query"
            type="search"
            placeholder="Search headphones, desks, kettles…"
            aria-label="Search products"
            className="h-9 w-full rounded-full border bg-muted/60 pr-3 pl-9 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          />
        </form>
        <nav className="ml-auto flex items-center gap-1" aria-label="Account">
          <ResetDemoButton />
          <Button variant="ghost" size="sm" asChild>
            <Link href="/orders">
              <PackageIcon />
              <span className="hidden lg:inline">Orders</span>
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/wishlist" aria-label={`Wishlist (${wishlistCount})`}>
              <HeartIcon />
              <span className="hidden lg:inline">Wishlist</span>
              {wishlistCount > 0 && <span className="text-xs text-muted-foreground tabular-nums">{wishlistCount}</span>}
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild className="relative">
            <Link href="/cart" aria-label={`Cart (${cartCount} items)`} data-testid="cart-link">
              <ShoppingCartIcon />
              <span className="hidden lg:inline">Cart</span>
              {cartCount > 0 && (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-[11px] font-semibold text-primary-foreground tabular-nums">
                  {cartCount}
                </span>
              )}
            </Link>
          </Button>
          <AssistantToggle />
        </nav>
      </div>
      <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-2 text-sm lg:px-6" aria-label="Categories">
        <Link href="/products" className="shrink-0 rounded-full px-3 py-1 text-muted-foreground hover:bg-muted hover:text-foreground">
          All products
        </Link>
        {CATEGORIES.map((c) => (
          <Link
            key={c}
            href={`/products?category=${encodeURIComponent(c)}`}
            className="shrink-0 rounded-full px-3 py-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {c}
          </Link>
        ))}
        <Link href="/products?on_sale=1" className="shrink-0 rounded-full px-3 py-1 font-medium text-[oklch(0.55_0.17_35)] hover:bg-muted">
          Deals
        </Link>
        {shopperName && <span className="ml-auto hidden shrink-0 py-1 text-xs text-muted-foreground lg:inline">Signed in as {shopperName}</span>}
      </nav>
    </header>
  )
}
