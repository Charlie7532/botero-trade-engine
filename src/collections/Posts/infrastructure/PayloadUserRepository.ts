import type { Payload } from 'payload'
import type { UserRepository } from '../domain/ports/UserRepository'
import type { AuthorPreview } from '../domain/models/AuthorPreview'

export class PayloadUserRepository implements UserRepository {
  constructor(private readonly payload: Payload) {}

  async getAuthorPreview(id: string | number): Promise<AuthorPreview | null> {
    try {
      const doc = await this.payload.findByID({
        collection: 'users',
        id,
        depth: 0,
      })

      if (!doc) {
        return null
      }

      return {
        id: doc.id,
        name: doc.name as string,
      }
    } catch {
      // Intentionally swallow errors to prevent breaking the read operation
      // if an author lookup fails.
      return null
    }
  }
}
