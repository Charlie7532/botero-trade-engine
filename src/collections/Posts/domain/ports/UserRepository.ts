import { AuthorPreview } from '../models/AuthorPreview'

export interface UserRepository {
  getAuthorPreview(id: string | number): Promise<AuthorPreview | null>
}
