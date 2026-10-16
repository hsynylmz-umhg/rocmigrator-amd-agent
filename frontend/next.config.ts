import type { NextConfig } from "next";

// The browser uses one origin for both HTTP and SSE. Keep the backend address
// server-side; do not expose credentials or runner connection settings here.
const backendUrl = new URL(process.env.BACKEND_URL ?? "http://127.0.0.1:8000");
if (!["http:", "https:"].includes(backendUrl.protocol) || backendUrl.username || backendUrl.password) {
  throw new Error("BACKEND_URL must be an HTTP(S) origin without credentials.");
}
if (backendUrl.pathname !== "/" || backendUrl.search || backendUrl.hash) {
  throw new Error("BACKEND_URL must be an origin without a path, query, or fragment.");
}

const config: NextConfig = {
  reactStrictMode: true,
  agentRules: false,
  turbopack: { root: process.cwd() },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl.origin}/api/:path*` }];
  },
};

export default config;
