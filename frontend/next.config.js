/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    // BACKEND_INTERNAL_URL is server-only (no NEXT_PUBLIC_ prefix, so Next
    // never inlines it into the browser bundle) - it's how the Next.js
    // server reaches FastAPI inside the Docker network (e.g.
    // http://backend:8000). Same-origin deployments (Cloudflare Tunnel ->
    // this frontend) set only this; leave NEXT_PUBLIC_API_URL unset so
    // frontend/lib/api.ts's client-side fetches use relative /api paths
    // against the one public hostname instead of baking the internal
    // backend URL into the browser bundle.
    //
    // Falls back to NEXT_PUBLIC_API_URL for deployments that intentionally
    // expose the backend on its own public origin (client calls it
    // directly, and this rewrite is redundant but harmless).
    const backendUrl = (
      process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL
    )?.replace(/\/$/, "");
    if (!backendUrl) return [];
    // Next's server (next start / standalone) proxies both plain HTTP and
    // WebSocket-upgrade requests for a rewritten destination - /ws/* works
    // the same way /api/* does, using the same http(s) destination scheme
    // (the WebSocket upgrade is itself an HTTP request; Next proxies it
    // based on the Upgrade header, not the destination's URL scheme - a
    // ws:// destination is not a documented/valid rewrite target).
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${backendUrl}/ws/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
