/**
 * Password Reset Email Template
 *
 * Sent when a user requests to reset their password via OTP.
 * Design: Minimalistic Apple-style
 */

import { COLORS, type SocialLink } from '../constants'
import { wrapInBaseTemplate } from '../baseTemplate'
import { getEmailTranslations, type SupportedLanguage } from '../translations'

export interface PasswordResetEmailParams {
    userName: string
    otp: string
    language?: SupportedLanguage
    socialLinks?: SocialLink[]
}

export interface PasswordResetEmailResult {
    subject: string
    html: string
}

/**
 * Generate password reset email with OTP
 */
export function generatePasswordResetEmail(params: PasswordResetEmailParams): PasswordResetEmailResult {
    const { userName, otp, language = 'en', socialLinks } = params
    const t = getEmailTranslations(language)

    const content = `
    <tr>
      <td style="text-align: center; padding-bottom: 32px;">
        <h1 style="margin: 0 0 12px 0; font-size: 28px; font-weight: 600; color: ${COLORS.text}; letter-spacing: -0.02em;">
          ${t.passwordReset.title}
        </h1>
        <p style="margin: 0; font-size: 17px; color: ${COLORS.textSecondary}; line-height: 1.5; letter-spacing: -0.01em;">
          ${t.greeting} ${userName}, ${t.passwordReset.intro}
        </p>
      </td>
    </tr>
    <tr>
      <td style="text-align: center; padding-bottom: 32px;">
        <div style="display: inline-block; background-color: ${COLORS.backgroundSecondary}; border-radius: 12px; padding: 20px 32px;">
          <span style="font-size: 32px; font-weight: 600; letter-spacing: 6px; color: ${COLORS.text}; font-family: 'SF Mono', SFMono-Regular, ui-monospace, Menlo, monospace;">
            ${otp}
          </span>
        </div>
      </td>
    </tr>
    <tr>
      <td style="text-align: center;">
        <p style="margin: 0 0 8px 0; font-size: 14px; color: ${COLORS.textTertiary}; letter-spacing: -0.01em;">
          ${t.passwordReset.expiresIn} <span style="color: ${COLORS.textSecondary};">10 ${language === 'es' ? 'minutos' : 'minutes'}</span>
        </p>
        <p style="margin: 0; font-size: 13px; color: ${COLORS.textTertiary}; letter-spacing: -0.01em;">
          ${t.passwordReset.warningMessage}
        </p>
      </td>
    </tr>
  `

    const html = wrapInBaseTemplate(content, {
        preheader: `${t.passwordReset.preheader}: ${otp}`,
        language,
        socialLinks,
    })

    return { subject: t.passwordReset.subject, html }
}
