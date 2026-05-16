import { cookies, headers } from 'next/headers'
import { cache } from 'react'
import { getPayload } from 'payload'
import config from '@payload-config'
import type { User } from '@/payload-types'

export const getUser = cache(async (): Promise<User | null> => {
    try {
        const cookieStore = await cookies()
        const token = cookieStore.get('payload-token')?.value

        if (!token) {
            return null
        }

        const payload = await getPayload({ config })

        const authHeaders = new Headers(await headers())
        authHeaders.set('Authorization', `JWT ${token}`)

        const { user } = await payload.auth({ headers: authHeaders })

        return user as User | null
    } catch (error) {
        console.error('Error getting user:', error)
        return null
    }
})

export async function isAuthenticated(): Promise<boolean> {
    const user = await getUser()
    return user !== null
}

export async function requireUser(): Promise<User> {
    const user = await getUser()
    if (!user) {
        throw new Error('Authentication required')
    }
    return user
}

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
