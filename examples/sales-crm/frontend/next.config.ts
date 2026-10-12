import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // The Relay Web SDK is a workspace package shipped as TypeScript source.
  transpilePackages: ["@relay/web-sdk"],
}

export default nextConfig
