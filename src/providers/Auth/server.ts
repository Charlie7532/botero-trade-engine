import { cookies, headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { cache } from 'react'
import { getPayload } from 'payload'
import config from '@payload-config'
import type { User } from '@/payload-types'

/**
 * Get the current authenticated user from request cookies.
 * Cached per request to avoid multiple Payload initializations.
 */
export const getUser = cache(async (): Promise<User | null> => {
    try {
        const cookieStore = await cookies()
        const token = cookieStore.get('payload-token')?.value

        if (!token) {
            return null
        }

        const payload = await getPayload({ config })

        // Verify the token and get user
        const { user } = await payload.auth({
            headers: await headers(),
        })

        return user as User | null
    } catch (error) {
        console.error('Error getting user:', error)
        return null
    }
})

/**
 * Check if the current request is authenticated.
 * For use in Server Components, API Routes, and Server Actions.
 */
export async function isAuthenticated(): Promise<boolean> {
    const user = await getUser()
    return user !== null
}

/**
 * Get user or throw an error if not authenticated.
 * Useful for protected Server Actions.
 * 
 * @throws Error if user is not authenticated
 */
export async function requireUser(): Promise<User> {
    const user = await getUser()
    if (!user) {
        throw new Error('Authentication required')
    }
    return user
}

/**
 * Get the current user session for server components.
 * Cached per request for performance.
 */
export const userSession = cache(async (): Promise<{
    user: User | null
    isAdmin: boolean
    isAuthenticated: boolean
}> => {
    const user = await getUser()
    const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

    return {
        user,
        isAdmin,
        isAuthenticated: user !== null,
    }
})

/**
 * Server-side counterpart to the `useUser()` hook from `./index.tsx`.
 *
 * Resolves the current user for a Server Component and redirects to
 * the login page when the session is missing or stale. The proxy
 * (`src/proxy.ts`) already blocks unauthenticated access to protected
 * routes; this helper handles the single case the proxy cannot detect:
 * a `payload-token` cookie that is present but no longer valid (stale
 * session, cross-subdomain mismatch, revoked user…). In that case we
 * redirect to `/login?clear=1&redirect=…`, which signals the proxy to
 * delete the stale cookie before showing the login form — this is what
 * breaks the redirect loop.
 */
export async function getServerUser(args?: {
    validUserRedirect?: string
}): Promise<{ token: string; user: User }> {
    const { validUserRedirect } = args || {}

    const cookieStore = await cookies()
    const token = cookieStore.get('payload-token')?.value

    const user = await getUser()

    if (validUserRedirect && user) {
        redirect(validUserRedirect)
    }

    if (!user) {
        redirect('/login?clear=1&redirect=%2Fportafolio')
    }

    return { token: token!, user }
}
