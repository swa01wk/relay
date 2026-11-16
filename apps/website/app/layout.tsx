import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"

import "./globals.css"

const sans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" })
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" })

export const metadata: Metadata = {
  title: "Relay — voice and text assistants that drive your app",
  description:
    "Relay lets your users talk to your product. Speech and text in; navigation, filters, forms and approved changes out — in your own UI.",
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} antialiased`}>
      <body className="min-h-dvh font-sans">{children}</body>
    </html>
  )
}
