import { NextRequest, NextResponse } from 'next/server'
import { getPayload } from 'payload'
import configPromise from '@payload-config'
import { verifyOtp, isOtpExpired, getMaxOtpAttempts } from '@/utilities/otp'
import { SignJWT } from 'jose'
import crypto from 'crypto'
import { getPostHogClient } from '@/lib/posthog-server'

interface VerifyOtpRequest {
    email: string
    otp: string
}

interface VerifyOtpResponse {
    success: boolean
    message?: string
    error?: string
}

/**
 * POST /api/auth/otp/verify
 * Verifies the OTP and logs in the user if valid
 */
export async function POST(request: NextRequest) {
    try {
        const body: VerifyOtpRequest = await request.json()
        const { email, otp } = body

        if (!email || !otp) {
            return NextResponse.json(
                { success: false, error: 'Email and OTP are required' },
                { status: 400 }
            )
        }

        // Validate OTP format (6 digits)
        if (!/^\d{6}$/.test(otp)) {
            return NextResponse.json(
                { success: false, error: 'Invalid verification code format' },
                { status: 400 }
            )
        }

        const payload = await getPayload({ config: configPromise })
        const normalizedEmail = email.toLowerCase().trim()

        // Find user by email with hidden fields
        const users = await payload.find({
            collection: 'users',
            where: {
                email: { equals: normalizedEmail },
            },
            limit: 1,
        })

        if (users.docs.length === 0) {
            return NextResponse.json(
                { success: false, error: 'Invalid verification code' },
                { status: 400 }
            )
        }

        const user = users.docs[0]!

        // Check if OTP exists
        if (!user.otpCode || !user.otpExpiry) {
            return NextResponse.json(
                { success: false, error: 'No verification code found. Please request a new one.' },
                { status: 400 }
            )
        }

        // Check if max attempts exceeded
        const maxAttempts = getMaxOtpAttempts()
        if ((user.otpAttempts || 0) >= maxAttempts) {
            return NextResponse.json(
                { success: false, error: 'Too many failed attempts. Please request a new code.' },
                { status: 429 }
            )
        }

        // Check if OTP has expired
        if (isOtpExpired(user.otpExpiry)) {
            return NextResponse.json(
                { success: false, error: 'Verification code has expired. Please request a new one.' },
                { status: 400 }
            )
        }

        // Verify OTP
        if (!verifyOtp(otp, user.otpCode)) {
            // Increment failed attempts
            await payload.update({
                collection: 'users',
                id: user.id,
                data: {
                    otpAttempts: (user.otpAttempts || 0) + 1,
                },
            })

            const remainingAttempts = maxAttempts - (user.otpAttempts || 0) - 1
            return NextResponse.json(
                {
                    success: false,
                    error: remainingAttempts > 0
                        ? `Invalid code. ${remainingAttempts} attempt${remainingAttempts === 1 ? '' : 's'} remaining.`
                        : 'Too many failed attempts. Please request a new code.'
                },
                { status: 400 }
            )
        }

        // OTP is valid - clear OTP fields and increment login count
        await payload.update({
            collection: 'users',
            id: user.id,
            data: {
                otpCode: null,
                otpExpiry: null,
                otpAttempts: 0,
                login_count: (user.login_count || 0) + 1,
            },
        })

        // Generate JWT token for passwordless login
        // This follows the same pattern as Payload uses internally
        // See: https://payloadcms.com/docs/authentication/jwt#external-jwt-validation
        const secret = crypto
            .createHash('sha256')
            .update(payload.config.secret)
            .digest('hex')
            .slice(0, 32)

        const tokenExpiration = 60 * 60 * 24 * 7 // 7 days in seconds

        const jwtToken = await new SignJWT({
            id: user.id,
            email: user.email,
            collection: 'users',
        })
            .setProtectedHeader({ alg: 'HS256' })
            .setExpirationTime(`${tokenExpiration}s`)
            .sign(new TextEncoder().encode(secret))

        // Track OTP verification and identify user server-side
        const posthogClient = getPostHogClient()
        posthogClient.capture({
            distinctId: String(user.id),
            event: 'otp_verified',
            properties: {
                email: normalizedEmail,
                loginCount: (user.login_count || 0) + 1,
            },
        })
        posthogClient.identify({
            distinctId: String(user.id),
            properties: {
                email: normalizedEmail,
                name: user.name,
                nickname: user.nickname,
                role: user.role,
            },
        })

        // Create response with auth cookie
        const response = NextResponse.json<VerifyOtpResponse>({
            success: true,
            message: 'Verification successful',
        })

        // Set the auth cookie (same format as Payload)
        const cookieName = `${payload.config.cookiePrefix || 'payload'}-token`
        response.cookies.set(cookieName, jwtToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            path: '/',
            maxAge: tokenExpiration,
        })

        return response
    } catch (error) {
        console.error('Error verifying OTP:', error)
        return NextResponse.json(
            { success: false, error: 'Failed to verify code' },
            { status: 500 }
        )
    }
}
