/**
 * Pure rules dictating dynamic routing paths for pages based on slugs.
 */

export function getPageWebPath(slug?: string | null): string {
  if (!slug) return '/'
  return slug === 'home' ? '/' : `/${slug}`
}
