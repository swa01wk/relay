import type { NextConfig } from "next"

// Experience Center: which sites may show this app in an iframe (space-separated origins).
const frameAncestors = process.env.RELAY_SANDBOX_FRAME_ANCESTORS?.trim()

const nextConfig: NextConfig = {
  // Experience Center sandbox helpers ship as TypeScript source.
  transpilePackages: ["@relay/example-sandbox"],
  // Docker images (infra/docker/Dockerfile.web) run the self-contained server Next builds.
  output: process.env.RELAY_NEXT_STANDALONE === "1" ? "standalone" : undefined,
  async headers() {
    if (!frameAncestors) return []
    return [{ source: "/:path*", headers: [{ key: "Content-Security-Policy", value: `frame-ancestors 'self' ${frameAncestors}` }] }]
  },
}

export default nextConfig
