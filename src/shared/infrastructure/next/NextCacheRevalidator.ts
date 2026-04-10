import { revalidatePath, revalidateTag } from 'next/cache'
import type { CacheRevalidator } from '../../domain/ports/CacheRevalidator'

/**
 * Shared Next.js App Router implementation of CacheRevalidator
 */
export class NextCacheRevalidator implements CacheRevalidator {
  revalidatePath(path: string): void {
    revalidatePath(path)
  }

  revalidateTag(tag: string): void {
    // This specific Next.js/Payload runtime typescript config expects 2 arguments here
    revalidateTag(tag, 'max')
  }
}
