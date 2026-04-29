/**
 * Email Utilities
 *
 * Helper functions for email generation including fetching
 * social links from SiteSettings.
 */

import { getPayload } from 'payload'
import config from '@payload-config'
import type { SocialLink, SocialPlatform } from './constants'

/**
 * Fetches social media links from SiteSettings global
 * Returns an array of SocialLink objects for use in email templates
 */
export async function getSocialLinksFromSettings(): Promise<SocialLink[]> {
    try {
        const payload = await getPayload({ config })
        const siteSettings = await payload.findGlobal({
            slug: 'site-settings',
        })

        const platforms = siteSettings?.socialMedia?.platforms

        if (!platforms || !Array.isArray(platforms)) {
            return []
        }

        return platforms
            .filter((p): p is { platform: SocialPlatform; url: string } =>
                Boolean(p?.platform && p?.url)
            )
            .map(({ platform, url }) => ({
                platform: platform as SocialPlatform,
                url,
            }))
    } catch (error) {
        console.error('Failed to fetch social links from SiteSettings:', error)
        return []
    }
}
