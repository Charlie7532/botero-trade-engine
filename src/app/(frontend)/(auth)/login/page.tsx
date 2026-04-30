import { getCachedSiteSettings } from '@/utilities/getSiteSettings'

import LoginPageClient from './LoginPageClient'

type LoginPageProps = {
    searchParams: Promise<{
        redirect?: string
    }>
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
    const params = await searchParams
    const siteSettings = await getCachedSiteSettings(0)()
    const allowNewUsers = siteSettings?.allowNewUsers !== false
    const redirectTo = params?.redirect || '/account'

    return <LoginPageClient redirectTo={redirectTo} allowNewUsers={allowNewUsers} />
}
