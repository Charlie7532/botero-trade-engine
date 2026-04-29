/**
 * Welcome Email Template
 *
 * Sent to new users when they create an account.
 * Design: Minimalistic Apple-style
 */

import { COLORS, getBaseUrl, type SocialLink } from '../constants'
import { wrapInBaseTemplate } from '../baseTemplate'
import { getEmailTranslations, type SupportedLanguage } from '../translations'

export interface WelcomeEmailParams {
    userName: string
    userEmail?: string
    loginUrl?: string
    language?: SupportedLanguage
    socialLinks?: SocialLink[]
}

export interface WelcomeEmailResult {
    subject: string
    html: string
}

/**
 * Generate welcome email for new users
 */
export function generateWelcomeEmail(params: WelcomeEmailParams): WelcomeEmailResult {
    const { userName, userEmail, loginUrl = `${getBaseUrl()}/login`, language = 'en', socialLinks } = params
    const t = getEmailTranslations(language)

    const content = `
    <!-- Title -->
    <tr>
      <td style="text-align: center; padding: 16px;">
        <h1 style="margin: 0; font-size: 28px; font-weight: 600; color: ${COLORS.text};">
          ${t.welcome.title}!
        </h1>
      </td>
    </tr>

    <!-- Body Content -->
    <tr>
      <td style="text-align: center; padding: 8px 16px 16px; line-height: 1.5; color: ${COLORS.text};">
        <p style="margin: 0 0 16px;">
          ${t.welcome.greeting} <strong>${userName}</strong>! ${t.welcome.introMessage}
          <strong>Enntra</strong> ${t.welcome.introSecure}
        </p>
      </td>
    </tr>

    <!-- Highlight Section -->
    <tr>
      <td style="padding: 0 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
          <tr>
            <td style="padding: 16px; font-size: 16px; font-weight: bold; color: ${COLORS.text}; background-color: ${COLORS.highlight}; border-radius: 8px; text-align: center;">
              ${t.welcome.highlightMessage}
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- CTA Button -->
    <tr>
      <td style="text-align: center; padding: 32px 16px;">
        <a href="${loginUrl}" style="display: inline-block; background-color: ${COLORS.primary}; color: ${COLORS.primaryText}; font-weight: 500; text-decoration: none; padding: 12px 32px; border-radius: 980px; font-size: 17px;">
          ${t.welcome.ctaButton}
        </a>
      </td>
    </tr>
  `

    const html = wrapInBaseTemplate(content, {
        preheader: t.welcome.preheader,
        language,
        socialLinks,
        userEmail,
    })

    return { subject: t.welcome.subject, html }
}
