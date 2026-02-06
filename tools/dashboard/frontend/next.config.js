/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker deployment
  output: 'standalone',
  // Note: NEXT_PUBLIC_* env vars are automatically exposed to browser
  // Set NEXT_PUBLIC_API_URL at runtime for remote deployments
  // Disable image optimization for external images
  images: {
    unoptimized: true,
  },
  // Suppress hydration warnings in development
  reactStrictMode: true,
  // Proxy API requests to backend when not using external proxy (Caddy)
  // This allows the frontend to work standalone without Caddy
  async rewrites() {
    // Only apply rewrites if NEXT_PUBLIC_API_URL is not set (using relative URLs)
    // When NEXT_PUBLIC_API_URL is set, the frontend makes direct requests
    if (process.env.NEXT_PUBLIC_API_URL) {
      return [];
    }
    // Use BACKEND_URL env var, or detect environment:
    // - Development (npm run dev): use localhost:8080
    // - Production (Docker): use backend:8080 (Docker network)
    const isDev = process.env.NODE_ENV === 'development';
    const backendUrl = process.env.BACKEND_URL || (isDev ? 'http://localhost:8080' : 'http://backend:8080');
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: '/ws',
        destination: `${backendUrl}/ws`,
      },
    ];
  },
};

module.exports = nextConfig;
