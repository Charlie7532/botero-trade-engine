/**
 * Password Changed Email Template
 *
 * Sent when a user successfully changes their password.
 * Design: Minimalistic Apple-style
 */

import { COLORS, getBaseUrl, type SocialLink } from '../constants'
import { wrapInBaseTemplate } from '../baseTemplate'
import { getEmailTranslations, type SupportedLanguage } from '../translations'

export interface PasswordChangedEmailParams {
    userName: string
    language?: SupportedLanguage
    socialLinks?: SocialLink[]
}

export interface PasswordChangedEmailResult {
    subject: string
    html: string
}

/**
 * Generate password changed confirmation email
 */
export function generatePasswordChangedEmail(
    params: PasswordChangedEmailParams
): PasswordChangedEmailResult {
    const { userName, language = 'en', socialLinks } = params
    const t = getEmailTranslations(language)

    const content = `
    <tr>
      <td style="text-align: center; padding-bottom: 24px;">
        <div style="width: 48px; height: 48px; background-color: ${COLORS.success}; border-radius: 50%; display: inline-block; line-height: 48px;">
          <span style="font-size: 24px; color: #ffffff;">✓</span>
        </div>
      </td>
    </tr>
    <tr>
      <td style="text-align: center; padding-bottom: 32px;">
        <h1 style="margin: 0 0 12px 0; font-size: 28px; font-weight: 600; color: ${COLORS.text}; letter-spacing: -0.02em;">
          ${t.passwordChanged.title}
        </h1>
        <p style="margin: 0; font-size: 17px; color: ${COLORS.textSecondary}; line-height: 1.5; letter-spacing: -0.01em;">
          ${t.greeting} ${userName}, ${t.passwordChanged.message}
        </p>
      </td>
    </tr>
    <tr>
      <td style="text-align: center; padding-bottom: 32px;">
        <a href="${getBaseUrl()}/login" style="display: inline-block; background-color: ${COLORS.primary}; color: ${COLORS.primaryText}; font-weight: 500; text-decoration: none; padding: 12px 24px; border-radius: 980px; font-size: 17px; letter-spacing: -0.01em;">
          ${t.passwordChanged.ctaButton}
        </a>
      </td>
    </tr>
    <tr>
      <td style="text-align: center;">
        <p style="margin: 0; font-size: 13px; color: ${COLORS.textTertiary}; letter-spacing: -0.01em;">
          ${t.passwordChanged.warningMessage}
        </p>
      </td>
    </tr>
  `

    const html = wrapInBaseTemplate(content, {
        preheader: t.passwordChanged.preheader,
        language,
        socialLinks,
    })

    return { subject: t.passwordChanged.subject, html }
}
