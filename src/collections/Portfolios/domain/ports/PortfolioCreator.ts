import type { UserPortfolioSummary } from './UserPortfolioReader'

export interface PortfolioCreator {
  create(input: { name: string; ownerId: number | string }): Promise<UserPortfolioSummary>
}
