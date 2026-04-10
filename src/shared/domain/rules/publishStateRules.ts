/**
 * Pure domain rules for determining default values for content publishing states.
 */

export function needsPublishedAtTimestamp(
  operation: string,
  currentPublishedAt?: string | Date | null,
): boolean {
  // Only auto-populate if we are creating or updating, and the field is entirely missing empty
  if (operation === 'create' || operation === 'update') {
    if (!currentPublishedAt) {
      return true
    }
  }

  return false
}
