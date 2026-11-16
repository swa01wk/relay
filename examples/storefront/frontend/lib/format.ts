const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" })

export const money = (value: number) => usd.format(value)

export const shortDate = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })

export const statusLabel = (status: string) => status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
