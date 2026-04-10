import type { CacheRevalidator } from '../../domain/ports/CacheRevalidator'

/**
 * Shared Use Case to revalidate the redirects state.
 * This instructs the caching layer to invalidate the 'redirects' tag.
 */
export function revalidateRedirectsState(cacheRevalidator: CacheRevalidator): void {
  cacheRevalidator.revalidateTag('redirects')
}
