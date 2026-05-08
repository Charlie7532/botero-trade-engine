import { NextRequest, NextResponse } from 'next/server'
import { getPayload } from 'payload'
import { headers } from 'next/headers'
import configPromise from '@payload-config'
import { generatePasswordChangedEmail, type SupportedLanguage } from '@/utilities/email'
import type { User } from '@/payload-types'

interface SetPasswordRequest {
    password: string
    confirmPassword: string
}

interface SetPasswordResponse {
    success: boolean
    message?: string
    error?: string
}

/**
 * POST /api/auth/set-password
 * Sets a new password for the authenticated user
 * Used by migrated users who don't have a password
 */
export async function POST(request: NextRequest) {
    try {
        const body: SetPasswordRequest = await request.json()
        const { password, confirmPassword } = body

        // Validate inputs
        if (!password || !confirmPassword) {
            return NextResponse.json(
                { success: false, error: 'Password and confirmation are required' },
                { status: 400 }
            )
        }

        if (password !== confirmPassword) {
            return NextResponse.json(
                { success: false, error: 'Passwords do not match' },
                { status: 400 }
            )
        }

        // Validate password strength - at least 2 out of 4 criteria
        const hasMinLength = password.length >= 8
        const hasUppercase = /[A-Z]/.test(password)
        const hasNumber = /\d/.test(password)
        const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>]/.test(password)

        const criteriaCount = [hasMinLength, hasUppercase, hasNumber, hasSpecialChar].filter(Boolean).length

        if (criteriaCount < 2) {
            return NextResponse.json(
                { success: false, error: 'Password must meet at least 2 of the following: 8+ characters, uppercase letter, number, special character' },
                { status: 400 }
            )
        }

        const payload = await getPayload({ config: configPromise })

        // Get the authenticated user from the request
        const headersList = await headers()
        const { user } = await payload.auth({ headers: headersList })

        if (!user) {
            return NextResponse.json(
                { success: false, error: 'You must be logged in to set a password' },
                { status: 401 }
            )
        }

        // Ensure user is a User (not an API key)
        if (!('email' in user) || !('id' in user)) {
            return NextResponse.json(
                { success: false, error: 'Invalid user type' },
                { status: 401 }
            )
        }

        // Update user with new password
        await payload.update({
            collection: 'users',
            id: user.id,
            data: {
                password,
                passwordSetAt: new Date().toISOString(),
                authProvider: 'payload', // Update auth provider since they now have a Payload password
            },
        })

        // Send password changed confirmation email
        try {
            const typedUser = user as User
            const userName = typedUser.name || typedUser.nickname || 'there'
            const language = (typedUser.preferredLanguage as SupportedLanguage) || 'en'
            const emailData = generatePasswordChangedEmail({ userName, language })

            await payload.sendEmail({
                to: typedUser.email,
                subject: emailData.subject,
                html: emailData.html,
            })
        } catch (emailError) {
            // Don't fail the request if email fails
            console.error('Failed to send password changed email:', emailError)
        }

        return NextResponse.json<SetPasswordResponse>({
            success: true,
            message: 'Password set successfully',
        })
    } catch (error) {
        console.error('Error setting password:', error)
        return NextResponse.json(
            { success: false, error: 'Failed to set password' },
            { status: 500 }
        )
    }
}
