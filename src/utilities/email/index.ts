/**
 * Email Utilities
 *
 * Centralized email template system with multi-language support.
 *
 * Usage:
 * ```typescript
 * import { generateOtpEmail, generateWelcomeEmail, getSocialLinksFromSettings } from '@/utilities/email'
 *
 * // Fetch social links from SiteSettings
 * const socialLinks = await getSocialLinksFromSettings()
 *
 * // Generate an OTP email in Spanish with social links
 * const { subject, html } = generateOtpEmail({
 *   userName: 'Juan',
 *   otp: '123456',
 *   language: 'es',
 *   socialLinks,
 * })
 *
 * await payload.sendEmail({ to: user.email, subject, html })
 * ```
 */

// Base template
export { wrapInBaseTemplate, type BaseTemplateOptions } from './baseTemplate'

// Constants
export {
    COLORS,
    SOCIAL_ICONS,
    getBaseUrl,
    type SocialLink,
    type SocialPlatform,
} from './constants'

// Utilities
export { getSocialLinksFromSettings } from './utils'

// Translations
export {
    getEmailTranslations,
    type SupportedLanguage,
    type EmailTranslations,
} from './translations'

// Templates
export { generateOtpEmail, type OtpEmailParams, type OtpEmailResult } from './templates/otp'

export {
    generateWelcomeEmail,
    type WelcomeEmailParams,
    type WelcomeEmailResult,
} from './templates/welcome'

export {
    generatePasswordResetEmail,
    type PasswordResetEmailParams,
    type PasswordResetEmailResult,
} from './templates/passwordReset'

export {
    generatePasswordChangedEmail,
    type PasswordChangedEmailParams,
    type PasswordChangedEmailResult,
} from './templates/passwordChanged'

/**
 * Legacy compatibility - emailTemplates object
 * @deprecated Use individual template functions instead
 */
export const emailTemplates = {
    otp: (params: { userName: string; otp: string; purpose?: 'login' | 'password-reset' }) => {
        const { generateOtpEmail } = require('./templates/otp')
        return generateOtpEmail(params).html
    },
    welcome: (params: { userName: string; loginUrl?: string }) => {
        const { generateWelcomeEmail } = require('./templates/welcome')
        return generateWelcomeEmail(params).html
    },
    passwordReset: (params: { userName: string; otp: string }) => {
        const { generatePasswordResetEmail } = require('./templates/passwordReset')
        return generatePasswordResetEmail(params).html
    },
    passwordChanged: (params: { userName: string }) => {
        const { generatePasswordChangedEmail } = require('./templates/passwordChanged')
        return generatePasswordChangedEmail(params).html
    },
}
