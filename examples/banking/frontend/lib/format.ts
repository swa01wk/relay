const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })

export const rupees = (value: number) => inr.format(value)

/** "₹1.2L" / "₹45K" for chart axes. */
export function compactRupees(value: number) {
  const abs = Math.abs(value)
  if (abs >= 100000) return `₹${(value / 100000).toFixed(abs >= 1000000 ? 0 : 1)}L`
  if (abs >= 1000) return `₹${Math.round(value / 1000)}K`
  return `₹${value}`
}

const TZ = "Asia/Kolkata"
const asDate = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00:00+05:30` : iso)

export const shortDate = (iso: string) => asDate(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: TZ })

export const mediumDate = (iso: string) => asDate(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: TZ })

export const longDate = (iso: string) => asDate(iso).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: TZ })

export const dateTime = (iso: string) =>
  asDate(iso).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZone: TZ })

export const monthLabel = (yyyyMm: string) => asDate(`${yyyyMm}-15`).toLocaleDateString("en-IN", { month: "short", year: "2-digit", timeZone: TZ })

export const longMonth = (yyyyMm: string) => asDate(`${yyyyMm}-15`).toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: TZ })

export const statusLabel = (status: string) => status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())

export const todayIst = () => new Date().toLocaleDateString("en-CA", { timeZone: TZ })

export const signed = (amount: number, direction: "debit" | "credit") => `${direction === "credit" ? "+" : "−"}${rupees(amount)}`
