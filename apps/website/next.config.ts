import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Docker images (infra/docker/Dockerfile.web) run the self-contained server Next builds.
  output: process.env.RELAY_NEXT_STANDALONE === "1" ? "standalone" : undefined,
}

export default nextConfig
