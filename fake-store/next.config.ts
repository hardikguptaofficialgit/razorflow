import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const monorepoRoot = path.join(rootDir, "..");

const nextConfig: NextConfig = {
  transpilePackages: [
    "@hardik21232323/razorflow-client",
    "@hardik21232323/razorflow-browser",
    "@hardik21232323/razorflow-protocol",
  ],
  turbopack: {
    root: monorepoRoot,
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.unsplash.com",
      },
      {
        protocol: "https",
        hostname: "framerusercontent.com",
      },
    ],
  },
};

export default nextConfig;
