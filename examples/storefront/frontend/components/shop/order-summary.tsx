import { money } from "@/lib/format"

export function OrderSummary({
  subtotal,
  discount,
  shipping,
  tax,
  total,
  coupon,
  children,
}: {
  subtotal: number
  discount: number
  shipping: number
  tax: number
  total: number
  coupon?: string | null
  children?: React.ReactNode
}) {
  const row = (label: React.ReactNode, value: string, strong = false) => (
    <div className={`flex justify-between ${strong ? "border-t pt-3 text-base font-semibold" : "text-muted-foreground"}`}>
      <span>{label}</span>
      <span className="tabular-nums text-foreground">{value}</span>
    </div>
  )
  return (
    <div className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-sm">
      {row("Subtotal", money(subtotal))}
      {discount > 0 && row(<>Discount{coupon ? ` (${coupon})` : ""}</>, `−${money(discount)}`)}
      {row("Shipping", shipping === 0 ? "Free" : money(shipping))}
      {row("Tax (8.25%)", money(tax))}
      {row("Total", money(total), true)}
      {children}
    </div>
  )
}
