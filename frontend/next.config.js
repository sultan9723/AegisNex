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
    // API requests are handled by app/api/[...path]/route.ts so the backend
    // URL is read at request time. Keep the WebSocket rewrite here; Next's
    // server proxies the HTTP Upgrade request using the configured scheme.
    return [
      {
        source: "/ws/:path*",
        destination: `${backendUrl}/ws/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
