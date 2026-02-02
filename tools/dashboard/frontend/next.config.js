/** @type {import('next').NextConfig} */
const nextConfig = {
  // API backend URL for server-side requests
  env: {
    API_URL: process.env.API_URL || 'http://localhost:8080',
    WS_URL: process.env.WS_URL || 'ws://localhost:8080',
  },
  // Disable image optimization for external images
  images: {
    unoptimized: true,
  },
  // Suppress hydration warnings in development
  reactStrictMode: true,
};

module.exports = nextConfig;
