import type { Metadata } from 'next'

import { cn } from '@/utilities/ui'
import { GeistMono } from 'geist/font/mono'
import { GeistSans } from 'geist/font/sans'
import React from 'react'

import { AdminBar } from '@/components/AdminBar'
import { Footer } from '@/modules/layout/interface/components/Footer/Component'
import { Header } from '@/modules/layout/interface/components/Header/Component'
import { Providers } from '@/providers'
import { DynamicColors } from '@/components/DynamicColors'
import { mergeOpenGraph } from '@/utilities/mergeOpenGraph'
import { draftMode } from 'next/headers'
import { getCachedSiteSettings } from '@/utilities/getSiteSettings'

import './globals.css'
import { getServerSideURL } from '@/utilities/getURL'

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { isEnabled } = await draftMode()

  // Get site settings for favicon and theme
  const siteSettings = await getCachedSiteSettings(1)()
  const customFavicon = siteSettings?.branding?.favicon?.url

  // Extract theme settings
  const themeSettings = siteSettings?.themeSettings
  const themeMode = themeSettings?.themeMode || 'both'
  const defaultTheme = themeSettings?.defaultTheme || 'system'

  return (
    <html className={cn(GeistSans.variable, GeistMono.variable)} lang="en" suppressHydrationWarning>
      <head>
        {/* Dynamic color styles from site settings */}
        <DynamicColors siteSettings={siteSettings} />
        {/* Use custom favicon from site settings or fallback to defaults */}
        {customFavicon ? (
          <link href={customFavicon} rel="icon" />
        ) : (
          <>
            <link href="/favicon.ico" rel="icon" sizes="32x32" />
            <link href="/favicon.svg" rel="icon" type="image/svg+xml" />
          </>
        )}
      </head>
      <body>
        <Providers
          themeMode={themeMode as 'light-only' | 'dark-only' | 'both'}
          defaultTheme={defaultTheme as 'light' | 'dark' | 'system'}
        >
          <AdminBar
            adminBarProps={{
              preview: isEnabled,
            }}
          />

          <Header />
          {children}
          <Footer />
        </Providers>
      </body>
    </html>
  )
}

export const metadata: Metadata = {
  metadataBase: new URL(getServerSideURL()),
  openGraph: mergeOpenGraph(),
  twitter: {
    card: 'summary_large_image',
    creator: '@payloadcms',
  },
}