import type { NextConfig } from "next";

// Experience Center: which sites may show this app in an iframe (space-separated origins, e.g.
// "http://localhost:3003 https://relay.example"). Unset: browsers' default (any site may frame it).
const frameAncestors = process.env.RELAY_SANDBOX_FRAME_ANCESTORS?.trim();

const nextConfig: NextConfig = {
  // Experience Center sandbox helpers ship as TypeScript source.
  transpilePackages: ["@relay/example-sandbox"],
  async headers() {
    if (!frameAncestors) return [];
    return [
      {
        source: "/:path*",
        headers: [{ key: "Content-Security-Policy", value: `frame-ancestors 'self' ${frameAncestors}` }],
      },
    ];
  },
};

export default nextConfig;
