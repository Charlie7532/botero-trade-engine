import type { Metadata } from 'next/types'

import React from 'react'
import { Search } from '@/search/Component'
import PageClient from './page.client'

type Args = {
  searchParams: Promise<{
    q: string
  }>
}
export default async function Page({ searchParams: searchParamsPromise }: Args) {
  void (await searchParamsPromise)

  return (
    <div className="pt-24 pb-24">
      <PageClient />
      <div className="container mb-16">
        <div className="prose dark:prose-invert max-w-none text-center">
          <h1 className="mb-8 lg:mb-16">Search</h1>

          <div className="max-w-[50rem] mx-auto">
            <Search />
          </div>
        </div>
      </div>

      <div className="container text-center text-gray-600">Search results are temporarily unavailable.</div>
    </div>
  )
}

export function generateMetadata(): Metadata {
  return {
    title: `Main 12 web Template Search`,
  }
}
