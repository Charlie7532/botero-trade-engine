import configPromise from '@payload-config'
import { getPayload } from 'payload'
import { cache } from 'react'

import { createGetUserPortfoliosUseCase } from '../application/useCases/getUserPortfolios'
import { createGetOrCreateDefaultPortfolioUseCase } from '../application/useCases/getOrCreateDefaultPortfolio'
import type { UserPortfolioSummary } from '../domain/ports/UserPortfolioReader'
import { createPayloadUserPortfolioReader } from '../infrastructure/PayloadUserPortfolioReader'
import { createPayloadPortfolioCreator } from '../infrastructure/PayloadPortfolioCreator'

export type { UserPortfolioSummary }

export const getUserPortfolios = cache(async (userId: number | string): Promise<UserPortfolioSummary[]> => {
  const payload = await getPayload({ config: configPromise })
  const reader = createPayloadUserPortfolioReader(payload)
  const execute = createGetUserPortfoliosUseCase(reader)

  return execute(userId)
})

export const getOrCreateDefaultPortfolio = async (
  userId: number | string,
  email: string,
): Promise<UserPortfolioSummary> => {
  const payload = await getPayload({ config: configPromise })
  const reader = createPayloadUserPortfolioReader(payload)
  const creator = createPayloadPortfolioCreator(payload)
  const execute = createGetOrCreateDefaultPortfolioUseCase(reader, creator)

  return execute(userId, email)
}

