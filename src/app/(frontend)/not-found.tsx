import Link from 'next/link'
import React from 'react'
import Layout from '@/app/(frontend)/layout'

export default function NotFound() {
  return (
    <Layout>
      <div className="min-h-screen flex flex-col items-center justify-center gap-6 px-4 text-center">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">
          Error 404
        </p>
        <h1 className="text-4xl font-semibold tracking-tight text-foreground">
          Page Not Found
        </h1>
        <p className="text-base text-muted max-w-xs leading-relaxed">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/"
          className="inline-flex items-center justify-center h-12 px-8 rounded-full bg-accent text-accent-foreground font-medium text-sm hover:opacity-90 transition-opacity"
        >
          Go home
        </Link>
      </div>
    </Layout>
  )
}