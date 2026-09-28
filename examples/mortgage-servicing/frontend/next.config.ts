import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@relay/web-sdk"],
};

export default nextConfig;
