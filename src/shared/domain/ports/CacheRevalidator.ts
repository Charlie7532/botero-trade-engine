/**
 * Core interface for executing framework cache invalidations.
 * This is located in the shared domain because multiple content collections
 * (Posts, Pages, etc.) rely on flushing HTTP caches without being coupled to Next.js.
 */
export interface CacheRevalidator {
  revalidatePath(path: string): void
  revalidateTag(tag: string): void
}
