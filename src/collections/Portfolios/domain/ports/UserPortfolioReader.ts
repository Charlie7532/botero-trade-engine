export type UserPortfolioSummary = {
  id: number | string
  slug: string
  name: string
  status: string
  role: string
}

export interface UserPortfolioReader {
  listByUserId(userId: number | string): Promise<UserPortfolioSummary[]>
}
