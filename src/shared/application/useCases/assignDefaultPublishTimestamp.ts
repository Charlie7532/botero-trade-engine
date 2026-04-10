import { needsPublishedAtTimestamp } from '../../domain/rules/publishStateRules'

/**
 * Ensures that any publishable entity receives a proper publication timestamp
 * if one was not initially provided by the client during creation or update.
 */
export function assignDefaultPublishTimestamp<T extends { publishedAt?: string | Date | null }>(
  data: T,
  operation: string,
  currentPublishedAt?: string | Date | null,
): T {
  if (needsPublishedAtTimestamp(operation, currentPublishedAt)) {
    return {
      ...data,
      publishedAt: new Date(),
    }
  }

  return data
}
