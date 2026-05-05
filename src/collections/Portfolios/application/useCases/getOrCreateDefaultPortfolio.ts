import type { UserPortfolioReader, UserPortfolioSummary } from '../../domain/ports/UserPortfolioReader'
import type { PortfolioCreator } from '../../domain/ports/PortfolioCreator'
import { buildDefaultPortfolioName } from '../../domain/rules/accountRules'

export function createGetOrCreateDefaultPortfolioUseCase(
  reader: UserPortfolioReader,
  creator: PortfolioCreator,
) {
  return async (userId: number | string, email: string): Promise<UserPortfolioSummary> => {
    const portfolios = await reader.listByUserId(userId)

    if (portfolios.length > 0) {
      return portfolios[0]!
    }

    const name = buildDefaultPortfolioName(email)
    return creator.create({ name, ownerId: userId })
  }
}
