import { getPayload } from 'payload'
import configPromise from '@payload-config'
import { unstable_cache } from 'next/cache'

// Type for site settings until types are regenerated
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SiteSettings = any

// Temporary function to get site settings until types are regenerated
async function getSiteSettings(depth = 0): Promise<SiteSettings | null> {
    try {
        const payload = await getPayload({ config: configPromise })

        const siteSettings = await payload.findGlobal({
            slug: 'site-settings' as const, // Type assertion until types are regenerated
            depth,
        })

        return siteSettings
    } catch (error) {
        console.warn('Site settings not found, using defaults:', error)
        return null
    }
}

/**
 * Returns a unstable_cache function mapped with the cache tag for site-settings
 */
export const getCachedSiteSettings = (depth = 0) =>
    unstable_cache(async () => getSiteSettings(depth), ['site-settings'], {
        tags: [`global_site-settings`],
    })