import { withPayload } from '@payloadcms/next/withPayload'
import { fileURLToPath } from 'url'

import redirects from './redirects.js'

const NEXT_PUBLIC_SERVER_URL = process.env.VERCEL_PROJECT_PRODUCTION_URL
  ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
  : undefined || process.env.NEXT_PUBLIC_SERVER_URL || 'http://localhost:3000'

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      // Add localhost for development
      {
        hostname: 'localhost',
        protocol: 'http',
      },
      ...[NEXT_PUBLIC_SERVER_URL /* 'https://example.com' */].map((item) => {
        const url = new URL(item)

        return {
          hostname: url.hostname,
          protocol: url.protocol.replace(':', ''),
        }
      }),
      // Add patterns for common blob storage providers
      {
        hostname: '*.vercel-storage.com',
        protocol: 'https',
      },
      {
        hostname: 'blob.vercel-storage.com',
        protocol: 'https',
      },
    ],
    // Optimize for logo quality and multiple sizes
    formats: ['image/avif', 'image/webp'],
    minimumCacheTTL: 3600, // Cache images for 1 hour
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048, 3840],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
    unoptimized: false, // Allow optimization globally but components can override
  },
  reactStrictMode: true,
  turbopack: {
    root: import.meta.dirname ?? fileURLToPath(new URL('.', import.meta.url)),
  },
  redirects,
}

export default withPayload(nextConfig, { devBundleServerPackages: false })
