import { cookies, headers } from 'next/headers'
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
    isOperator: boolean
    isAuthenticated: boolean
}> => {
    const user = await getUser()
    const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'
    const isOperator = user?.role === 'operator' || user?.role === 'admin' || user?.role === 'superadmin'

    return {
        user,
        isAdmin,
        isOperator,
        isAuthenticated: user !== null,
    }
})
