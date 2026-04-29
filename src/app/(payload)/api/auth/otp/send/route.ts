import { NextRequest, NextResponse } from 'next/server'
import { getPayload } from 'payload'
import configPromise from '@payload-config'
import { generateOtp, hashOtp, getOtpExpiry } from '@/utilities/otp'
import {
    generateOtpEmail,
    generatePasswordResetEmail,
    type SupportedLanguage,
} from '@/utilities/email'

interface SendOtpRequest {
    email: string
    purpose?: 'login' | 'password-reset'
}

interface SendOtpResponse {
    success: boolean
    message: string
}

/**
 * POST /api/auth/otp/send
 * Generates and sends an OTP to the user's email
 * Used for migrated users who don't have a password
 */
export async function POST(request: NextRequest) {
    try {
        const body: SendOtpRequest = await request.json()
        const { email, purpose = 'login' } = body

        if (!email || typeof email !== 'string') {
            return NextResponse.json(
                { success: false, message: 'Email is required' },
                { status: 400 }
            )
        }

        const payload = await getPayload({ config: configPromise })
        const normalizedEmail = email.toLowerCase().trim()

        // Find user by email
        const users = await payload.find({
            collection: 'users',
            where: {
                email: { equals: normalizedEmail },
            },
            limit: 1,
        })

        if (users.docs.length === 0) {
            // Don't reveal if user exists or not for security
            return NextResponse.json<SendOtpResponse>({
                success: true,
                message: 'If your email is registered, you will receive a verification code.',
            })
        }

        const user = users.docs[0]!

        // Generate OTP
        const otp = generateOtp()
        const hashedOtp = hashOtp(otp)
        const otpExpiry = getOtpExpiry()

        // Store hashed OTP in database
        await payload.update({
            collection: 'users',
            id: user.id,
            data: {
                otpCode: hashedOtp,
                otpExpiry: otpExpiry.toISOString(),
                otpAttempts: 0, // Reset attempts on new OTP
            },
        })

        // Get user's name and language for personalized email
        const userName = user.name || user.nickname || 'there'
        const language = (user.preferredLanguage as SupportedLanguage) || 'en'

        // Generate email based on purpose
        const emailData =
            purpose === 'password-reset'
                ? generatePasswordResetEmail({ userName, otp, language })
                : generateOtpEmail({ userName, otp, purpose, language })

        // Send OTP email
        await payload.sendEmail({
            to: normalizedEmail,
            subject: emailData.subject,
            html: emailData.html,
        })

        return NextResponse.json<SendOtpResponse>({
            success: true,
            message: 'Verification code sent to your email.',
        })
    } catch (error) {
        console.error('Error sending OTP:', error)
        return NextResponse.json(
            { success: false, message: 'Failed to send verification code' },
            { status: 500 }
        )
    }
}
