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
};

module.exports = nextConfig;
