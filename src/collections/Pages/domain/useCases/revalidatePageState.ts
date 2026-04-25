import type { CacheRevalidator } from '@/shared/domain/ports/CacheRevalidator'
import {
  isCurrentlyPublished,
  isNewlyUnpublished,
  requiresRevalidationOnDelete,
  requiresRevalidationOnUpdate,
} from '../../../Posts/domain/rules/revalidationRules'
import { getPageWebPath } from '../rules/pageRouteRules'

export interface RevalidationPayloadLogger {
  info(msg: string): void
}

/**
 * Orchestrates cache flushing for Pages, delegating the path rules
 * to the Page domain and executing through the generic cache port.
 */
export function revalidatePageStateOnUpdate(
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
    const path = getPageWebPath(currentDoc.slug)
    logger.info(`Revalidating page at path: ${path}`)
    cacheRevalidator.revalidatePath(path)
    cacheRevalidator.revalidateTag('pages-sitemap')
  }

  // If newly unpublished (was published, now draft), we must flush the old slug cache
  if (previousDoc && isNewlyUnpublished(currentDoc._status, previousDoc._status)) {
    const oldPath = getPageWebPath(previousDoc.slug)
    logger.info(`Revalidating old page at path: ${oldPath}`)
    cacheRevalidator.revalidatePath(oldPath)
    cacheRevalidator.revalidateTag('pages-sitemap')
  }
}

/**
 * Handles cache invalidation when a Page is hard-deleted from the database.
 */
export function revalidatePageStateOnDelete(
  deletedDoc: { slug?: string | null; _status?: string | null },
  cacheRevalidator: CacheRevalidator,
): void {
  if (requiresRevalidationOnDelete()) {
    const path = getPageWebPath(deletedDoc?.slug)
    cacheRevalidator.revalidatePath(path)
    cacheRevalidator.revalidateTag('pages-sitemap')
  }
}
