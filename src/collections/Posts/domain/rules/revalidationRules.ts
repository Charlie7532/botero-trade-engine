/**
 * Pure rules to determine if a Post state change warrants a cache revalidation
 */

export function requiresRevalidationOnUpdate(
  currentStatus?: string | null,
  previousStatus?: string | null,
): boolean {
  // If moving into published state, or already published and updated
  if (currentStatus === 'published') return true
  
  // If moving out of published state (it was published, now it is draft/archived)
  if (previousStatus === 'published' && currentStatus !== 'published') return true

  return false
}

export function requiresRevalidationOnDelete(): boolean {
  // Always true for now unless we introduce soft deletes
  return true
}

export function isNewlyUnpublished(
  currentStatus?: string | null,
  previousStatus?: string | null,
): boolean {
  return previousStatus === 'published' && currentStatus !== 'published'
}

export function isCurrentlyPublished(currentStatus?: string | null): boolean {
  return currentStatus === 'published'
}
