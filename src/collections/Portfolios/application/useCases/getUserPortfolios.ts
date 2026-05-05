import type { UserPortfolioReader, UserPortfolioSummary } from '../../domain/ports/UserPortfolioReader'

export function createGetUserPortfoliosUseCase(reader: UserPortfolioReader) {
  return async (userId: number | string): Promise<UserPortfolioSummary[]> => {
    return reader.listByUserId(userId)
  }
}
