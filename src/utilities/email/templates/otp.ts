/**
 * OTP Email Template
 *
 * Used for sending verification codes for login or password reset.
 * Design: Minimalistic Apple-style
 */

import { COLORS, type SocialLink } from '../constants'
import { wrapInBaseTemplate } from '../baseTemplate'
import { getEmailTranslations, type SupportedLanguage } from '../translations'

export interface OtpEmailParams {
    userName: string
    otp: string
    purpose?: 'login' | 'password-reset'
    language?: SupportedLanguage
    socialLinks?: SocialLink[]
}

export interface OtpEmailResult {
    subject: string
    html: string
}

/**
 * Generate OTP verification email
 */
export function generateOtpEmail(params: OtpEmailParams): OtpEmailResult {
    const { userName, otp, purpose = 'login', language = 'en', socialLinks } = params
    const t = getEmailTranslations(language)

    const purposeText = purpose === 'password-reset' ? t.otp.purposePasswordReset : t.otp.purposeLogin

    const subject =
        purpose === 'password-reset'
            ? `${t.otp.subjectPasswordReset}: ${otp}`
            : `${t.otp.subjectLogin}: ${otp}`

    const content = `
    <tr>
      <td style="text-align: center; padding-bottom: 32px;">
        <h1 style="margin: 0 0 12px 0; font-size: 28px; font-weight: 600; color: ${COLORS.text}; letter-spacing: -0.02em;">
          ${t.greeting} ${userName}
        </h1>
        <p style="margin: 0; font-size: 17px; color: ${COLORS.textSecondary}; line-height: 1.5; letter-spacing: -0.01em;">
          ${purposeText}
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
          ${t.otp.expiresIn} <span style="color: ${COLORS.textSecondary};">10 ${language === 'es' ? 'minutos' : 'minutes'}</span>
        </p>
        <p style="margin: 0; font-size: 13px; color: ${COLORS.textTertiary}; letter-spacing: -0.01em;">
          ${t.otp.ignoreMessage}
        </p>
      </td>
    </tr>
  `

    const html = wrapInBaseTemplate(content, {
        preheader: `${t.otp.preheader}: ${otp}`,
        language,
        socialLinks,
    })

    return { subject, html }
}
