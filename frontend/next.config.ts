import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Dev convenience: when API_PROXY_TARGET is set, /backend/* is proxied to the API so the
  // whole app is reachable through the Next port alone (single-port sandboxes, tunnels).
  // Inert in normal dev and in prod builds where the variable is unset.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    if (!target) return [];
    return [{ source: "/backend/:path*", destination: `${target}/:path*` }];
  },
};

export default nextConfig;
