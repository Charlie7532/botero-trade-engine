import type { CacheRevalidator } from '../../../../shared/domain/ports/CacheRevalidator'

export interface RevalidationPayloadLogger {
  info(msg: string): void
}

/**
 * Orchestrates cache flushing for global Layout elements (Header, Footer).
 */
export function revalidateHeaderState(
  cacheRevalidator: CacheRevalidator,
  logger: RevalidationPayloadLogger,
): void {
  logger.info(`Revalidating header`)
  cacheRevalidator.revalidateTag('global_header')
}

export function revalidateFooterState(
  cacheRevalidator: CacheRevalidator,
  logger: RevalidationPayloadLogger,
): void {
  logger.info(`Revalidating footer`)
  cacheRevalidator.revalidateTag('global_footer')
}

export function revalidateSiteSettingsState(
  cacheRevalidator: CacheRevalidator,
  logger: RevalidationPayloadLogger,
): void {
  logger.info(`Revalidating site-settings`)
  cacheRevalidator.revalidateTag('global_site-settings')
}
