/**
 * Base Email Template
 *
 * Provides the wrapper template with header (logo) and footer
 * that is used by all email templates.
 * 
 * Design: Minimalistic Apple-style
 */

import { COLORS, SOCIAL_ICONS, getBaseUrl, type SocialLink, type SocialPlatform } from './constants'
import { getEmailTranslations, type SupportedLanguage } from './translations'

/**
 * Generates the minimal email header with logo
 */
function getEmailHeader(): string {
    return `
    <tr>
      <td style="padding: 24px 8px; text-align: center;">
        <img src="${getBaseUrl()}/assets/logo/logo_enntra_black.png" alt="Enntra" width="200" style="max-width: 200px; height: auto; display: block; margin: 0 auto;">
      </td>
    </tr>
  `
}

/**
 * Generates social media icons section
 */
function getSocialSection(socialLinks: SocialLink[]): string {
    if (!socialLinks || socialLinks.length === 0) {
        return ''
    }

    const iconsHtml = socialLinks
        .map(({ platform, url }) => {
            const icon = SOCIAL_ICONS[platform as SocialPlatform]
            if (!icon) return ''

            return `
        <a href="${url}" target="_blank" rel="noopener" style="display: inline-block; width: 40px; height: 40px; margin: 0 6px; color: ${COLORS.textTertiary}; text-decoration: none;">
          ${icon}
        </a>
      `
        })
        .filter(Boolean)
        .join('')

    return `
    <tr>
      <td style="padding: 0 0 24px 0; text-align: center;">
        ${iconsHtml}
      </td>
    </tr>
  `
}

/**
 * Generates the minimal email footer
 */
function getEmailFooter(language: SupportedLanguage = 'en', socialLinks?: SocialLink[], userEmail?: string): string {
    const t = getEmailTranslations(language)
    const currentYear = new Date().getFullYear()

    const emailSentTo = userEmail
        ? `<p style="margin: 16px 0 0; font-size: 14px; color: ${COLORS.textSecondary}; line-height: 1.5;">
        ${t.footerEmailSentTo} <strong>${userEmail}</strong>. ${t.footerSecurityNotice}
      </p>`
        : ''

    return `
    <tr>
      <td style="padding: 16px; text-align: center; color: ${COLORS.textSecondary}; font-size: 14px; line-height: 1.5;">
        <p style="margin: 0;">
          ${t.footerContactMessage}
          <a href="mailto:info@enntra.com" style="color: ${COLORS.text}; text-decoration: none; font-weight: bold;">info@enntra.com</a>
        </p>
        ${emailSentTo}
      </td>
    </tr>
    ${getSocialSection(socialLinks || [])}
    <tr>
      <td style="padding: 16px 0 32px 0; text-align: center;">
        <p style="margin: 0 0 8px 0; font-size: 12px; color: ${COLORS.textTertiary}; letter-spacing: -0.01em;">
          © ${currentYear} Enntra. ${t.footerCopyright}
        </p>
        <p style="margin: 0; font-size: 12px; color: ${COLORS.textTertiary}; letter-spacing: -0.01em;">
          ${t.footerTagline}
        </p>
      </td>
    </tr>
  `
}

export interface BaseTemplateOptions {
    preheader?: string
    language?: SupportedLanguage
    socialLinks?: SocialLink[]
    userEmail?: string
}

/**
 * Wraps content in the base email template with header and footer
 */
export function wrapInBaseTemplate(content: string, options: BaseTemplateOptions = {}): string {
    const { preheader, language = 'en', socialLinks, userEmail } = options

    const preheaderHtml = preheader
        ? `<span style="display: none; font-size: 1px; color: #ffffff; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden;">${preheader}</span>`
        : ''

    return `
<!DOCTYPE html>
<html lang="${language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>Enntra</title>
  <!--[if mso]>
  <style type="text/css">
    table {border-collapse: collapse;}
  </style>
  <![endif]-->
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: ${COLORS.background}; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;">
  ${preheaderHtml}
  
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: ${COLORS.background};">
    <tr>
      <td style="padding: 0 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto;">
          ${getEmailHeader()}
          ${content}
          ${getEmailFooter(language, socialLinks, userEmail)}
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
  `.trim()
}
