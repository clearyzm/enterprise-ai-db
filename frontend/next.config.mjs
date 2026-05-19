/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker production builds
  output: 'standalone',

  // Rewrites allow Next.js server-side code to call backend without CORS issues.
  // Client-side code uses NEXT_PUBLIC_API_URL directly (set in docker-compose.yml).
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
    ];
  },

  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
  },
};

export default nextConfig;
