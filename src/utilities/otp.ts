import crypto from 'crypto'

const OTP_TTL_MINUTES = 10
const OTP_MAX_ATTEMPTS = 5

export function generateOtp(length = 6): string {
    const min = 10 ** (length - 1)
    const max = 10 ** length - 1
    return String(Math.floor(Math.random() * (max - min + 1)) + min)
}

export function hashOtp(otp: string): string {
    return crypto.createHash('sha256').update(otp).digest('hex')
}

export function verifyOtp(plainOtp: string, hashedOtp: string): boolean {
    return hashOtp(plainOtp) === hashedOtp
}

export function getOtpExpiry(fromDate = new Date()): Date {
    return new Date(fromDate.getTime() + OTP_TTL_MINUTES * 60 * 1000)
}

export function isOtpExpired(expiry: string | Date): boolean {
    const expiryDate = expiry instanceof Date ? expiry : new Date(expiry)
    return Number.isNaN(expiryDate.getTime()) || expiryDate.getTime() < Date.now()
}

export function getMaxOtpAttempts(): number {
    return OTP_MAX_ATTEMPTS
}
