import { unstable_cache } from 'next/cache'

type RedirectDoc = {
  from?: string | null
  to?: {
    url?: string | null
    reference?: {
      relationTo?: string | null
      value?: { slug?: string | null } | string | null
    } | null
  } | null
}

// No Redirects collection in this project — always returns empty
export async function getRedirects(): Promise<RedirectDoc[]> {
  return []
}

/**
 * Returns a unstable_cache function mapped with the cache tag for 'redirects'.
 */
export const getCachedRedirects = () =>
  unstable_cache(async () => getRedirects(), ['redirects'], {
    tags: ['redirects'],
  })
