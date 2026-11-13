const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })

export const rupees = (value: number) => inr.format(value)

const TZ = "Asia/Kolkata"
const asDate = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00:00+05:30` : iso)

export const shortDate = (iso: string) => asDate(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: TZ })

export const dayDate = (iso: string) => asDate(iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: TZ })

export const longDate = (iso: string) =>
  asDate(iso).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: TZ })

export const dateTime = (iso: string) =>
  asDate(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true, timeZone: TZ })

/** "12–15 Dec" or "30 Dec – 2 Jan". */
export function dateRange(checkIn: string, checkOut: string) {
  const a = asDate(checkIn)
  const b = asDate(checkOut)
  const sameMonth = a.getMonth() === b.getMonth()
  return sameMonth
    ? `${a.getDate()}–${b.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: TZ })}`
    : `${shortDate(checkIn)} – ${shortDate(checkOut)}`
}

export const statusLabel = (status: string) => status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())

export const todayIst = () => new Date().toLocaleDateString("en-CA", { timeZone: TZ })

export const addDays = (isoDate: string, days: number) => {
  const d = new Date(`${isoDate}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export const nightsBetween = (a: string, b: string) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 86_400_000)

export function guestsLabel(g: { adults: number; children?: number; infants?: number; pets?: number }) {
  const people = g.adults + (g.children ?? 0)
  const parts = [`${people} guest${people === 1 ? "" : "s"}`]
  if (g.infants) parts.push(`${g.infants} infant${g.infants === 1 ? "" : "s"}`)
  if (g.pets) parts.push(`${g.pets} pet${g.pets === 1 ? "" : "s"}`)
  return parts.join(", ")
}
