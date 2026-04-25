import type { UserRepository } from '../ports/UserRepository'
import type { AuthorPreview } from '../models/AuthorPreview'

/**
 * Given a list of author references from a post, securely fetches and maps 
 * exactly the required public data for each author, guaranteeing no private user logic leaks.
 */
export async function populatePublicAuthors(
  authorRefs: any[],
  userRepo: UserRepository,
): Promise<AuthorPreview[]> {
  if (!authorRefs || authorRefs.length === 0) {
    return []
  }

  const authorDocs: AuthorPreview[] = []

  for (const author of authorRefs) {
    const id = typeof author === 'object' ? author?.id : author
    if (!id) continue

    const authorDoc = await userRepo.getAuthorPreview(id)
    if (authorDoc) {
      authorDocs.push(authorDoc)
    }
  }

  return authorDocs
}
