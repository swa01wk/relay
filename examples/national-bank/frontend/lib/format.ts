/** ₹1,23,456.00 — Indian digit grouping, two decimals like a passbook. */
export function inr(value: number | null | undefined, decimals = true): string {
  if (value === null || value === undefined) return ""
  return (value < 0 ? "-" : "") + Math.abs(value).toLocaleString("en-IN", { minimumFractionDigits: decimals ? 2 : 0, maximumFractionDigits: decimals ? 2 : 0 })
}

/** ₹1,23,456 */
export function rupees(value: number | null | undefined): string {
  if (value === null || value === undefined) return ""
  return `₹${inr(value, false)}`
}

/** 2026-11-19 → 19-11-2026 (dates are shown the way bank statements show them). */
export function dmy(iso: string | null | undefined): string {
  if (!iso) return ""
  const [y, m, d] = iso.slice(0, 10).split("-")
  return `${d}-${m}-${y}`
}

/** 2026-11-19 → 19 Nov 2026 */
export function longDate(iso: string | null | undefined): string {
  if (!iso) return ""
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
}

/** Today's date in India, YYYY-MM-DD. */
export function todayIst(): string {
  return new Date(Date.now() + 5.5 * 3600 * 1000).toISOString().slice(0, 10)
}
