import configPromise from '@payload-config'
import { getPayload } from 'payload'
import { cache } from 'react'

import { createGetUserPortfoliosUseCase } from './domain/useCases/getUserPortfolios'
import type { UserPortfolioSummary } from './domain/ports/UserPortfolioReader'
import { createPayloadUserPortfolioReader } from './infrastructure/PayloadUserPortfolioReader'

export type { UserPortfolioSummary }

export const getUserPortfolios = cache(async (userId: number | string): Promise<UserPortfolioSummary[]> => {
  const payload = await getPayload({ config: configPromise })
  const reader = createPayloadUserPortfolioReader(payload)
  const execute = createGetUserPortfoliosUseCase(reader)

  return execute(userId)
})
