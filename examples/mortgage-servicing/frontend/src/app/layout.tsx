import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Relay Mortgage Shell",
  description: "Phase 0 — health and dev session connection",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
