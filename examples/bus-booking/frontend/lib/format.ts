const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })

export const rupees = (value: number) => inr.format(value)

/** Times are IST; the API sends ISO strings with +05:30, shown in IST whatever the browser's zone. */
const TZ = "Asia/Kolkata"

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: TZ })

export const shortDate = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T12:00:00+05:30` : iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: TZ })

export const longDate = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T12:00:00+05:30` : iso).toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: TZ,
  })

export const dateTime = (iso: string) => `${shortDate(iso)}, ${time(iso)}`

export const statusLabel = (status: string) => status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())

/** Today's date in IST as YYYY-MM-DD. */
export const todayIst = () => new Date().toLocaleDateString("en-CA", { timeZone: TZ })

export const addDays = (isoDate: string, days: number) => {
  const d = new Date(`${isoDate}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}
