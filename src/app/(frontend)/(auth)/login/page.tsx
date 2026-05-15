import { getCachedSiteSettings } from '@/utilities/getSiteSettings'

import LoginPageClient from './LoginPageClient'

function resolveRedirectTarget(redirect?: string): string {
    if (!redirect || !redirect.startsWith('/') || redirect.startsWith('//')) {
        return '/portafolio'
    }

    if (redirect === '/login' || redirect.startsWith('/login?') || redirect === '/admin/login') {
        return '/portafolio'
    }

    return redirect
}

type LoginPageProps = {
    searchParams: Promise<{
        redirect?: string
    }>
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
    const params = await searchParams
    const siteSettings = await getCachedSiteSettings(0)()
    const allowNewUsers = siteSettings?.allowNewUsers !== false
    const redirectTo = resolveRedirectTarget(params?.redirect)

    return <LoginPageClient redirectTo={redirectTo} allowNewUsers={allowNewUsers} />
}
