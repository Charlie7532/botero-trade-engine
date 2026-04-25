import type { CacheRevalidator } from '@/shared/domain/ports/CacheRevalidator'
import {
  isCurrentlyPublished,
  isNewlyUnpublished,
  requiresRevalidationOnDelete,
  requiresRevalidationOnUpdate,
} from '../rules/revalidationRules'

export interface RevalidationPayloadLogger {
  info(msg: string): void
}

/**
 * Evaluates the domain rules to determine if the post state change warrants
 * flushing the application cache, and orchestrates the cache flush via the provided port.
 */
export function revalidatePostStateOnUpdate(
  currentDoc: { slug?: string | null; _status?: string | null },
  previousDoc: { slug?: string | null; _status?: string | null } | undefined,
  cacheRevalidator: CacheRevalidator,
  logger: RevalidationPayloadLogger,
): void {
  if (
    !requiresRevalidationOnUpdate(currentDoc._status, previousDoc?._status)
  ) {
    return
  }

  // Revalidate current published state
  if (isCurrentlyPublished(currentDoc._status)) {
    const path = `/posts/${currentDoc.slug}`
    logger.info(`Revalidating post at path: ${path}`)
    cacheRevalidator.revalidatePath(path)
    cacheRevalidator.revalidateTag('posts-sitemap')
  }

  // If newly unpublished (was published, now draft), we must flush the old slug cache
  if (previousDoc && isNewlyUnpublished(currentDoc._status, previousDoc._status)) {
    const oldPath = `/posts/${previousDoc.slug}`
    logger.info(`Revalidating old post at path: ${oldPath}`)
    cacheRevalidator.revalidatePath(oldPath)
    cacheRevalidator.revalidateTag('posts-sitemap')
  }
}

/**
 * Handles cache invalidation when a Post is hard-deleted from the database.
 */
export function revalidatePostStateOnDelete(
  deletedDoc: { slug?: string | null; _status?: string | null },
  cacheRevalidator: CacheRevalidator,
): void {
  if (requiresRevalidationOnDelete()) {
    const path = `/posts/${deletedDoc?.slug}`
    cacheRevalidator.revalidatePath(path)
    cacheRevalidator.revalidateTag('posts-sitemap')
  }
}
