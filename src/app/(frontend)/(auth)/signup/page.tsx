import { redirect } from 'next/navigation'

import { getCachedSiteSettings } from '@/utilities/getSiteSettings'

import SignupPageClient from './SignupPageClient'

export default async function SignupPage() {
  const siteSettings = await getCachedSiteSettings(0)()

  if (siteSettings?.allowNewUsers === false) {
    redirect('/login')
  }

  return <SignupPageClient />
}
