import { NextRequest, NextResponse } from 'next/server'
import { getPayload } from 'payload'
import configPromise from '@payload-config'

interface CheckEmailRequest {
    email: string
}

interface CheckEmailResponse {
    exists: boolean
    hasPassword: boolean
    authProvider: string | null
}

/**
 * POST /api/auth/check-email
 * Checks if a user exists and whether they have a password set
 * Used in the two-step login flow to determine next action
 */
export async function POST(request: NextRequest) {
    try {
        const body: CheckEmailRequest = await request.json()
        const { email } = body

        if (!email || typeof email !== 'string') {
            return NextResponse.json(
                { error: 'Email is required' },
                { status: 400 }
            )
        }

        const payload = await getPayload({ config: configPromise })

        // Find user by email
        const users = await payload.find({
            collection: 'users',
            where: {
                email: { equals: email.toLowerCase().trim() },
            },
            limit: 1,
        })

        if (users.docs.length === 0) {
            return NextResponse.json<CheckEmailResponse>({
                exists: false,
                hasPassword: false,
                authProvider: null,
            })
        }

        const user = users.docs[0]!

        // Check if user has a password set
        // Users without passwords are migrated users or OAuth-only users
        // We check passwordSetAt to determine if they've set a password in Payload
        const hasPassword = Boolean(user.passwordSetAt)
        const authProvider = user.authProvider || 'payload'

        return NextResponse.json<CheckEmailResponse>({
            exists: true,
            hasPassword,
            authProvider,
        })
    } catch (error) {
        console.error('Error checking email:', error)
        return NextResponse.json(
            { error: 'Failed to check email' },
            { status: 500 }
        )
    }
}
