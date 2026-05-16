'use server'

import configPromise from '@payload-config'
import { getPayload } from 'payload'
import type { RequiredDataFromCollectionSlug } from 'payload'
import { revalidatePath } from 'next/cache'

import { userSession } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import type {
  BrokerType,
  Department,
  PortfolioEnvironment,
} from '@/collections/BrokerAccounts/domain/rules/portfolioRules'

export type CreateBrokerAccountInput = {
  portfolioSlug: string
  name: string
  brokerType: BrokerType
  environment: PortfolioEnvironment
  department: Department
  // Alpaca
  apiKeyPlaintext?: string
  secretKeyPlaintext?: string
  alpacaBaseUrl?: string
  // Interactive Brokers
  ibAccountId?: string
  ibHost?: string
  ibPort?: number
  ibClientId?: number
}

export type CreateBrokerAccountResult =
  | { ok: true; id: string | number }
  | { ok: false; error: string }

const trim = (value: string | undefined): string | undefined => {
  if (!value) return undefined
  const t = value.trim()
  return t.length === 0 ? undefined : t
}

export async function createBrokerAccount(
  input: CreateBrokerAccountInput,
): Promise<CreateBrokerAccountResult> {
  const { user } = await userSession()
  if (!user) return { ok: false, error: 'Not authenticated.' }

  const name = trim(input.name)
  if (!name) return { ok: false, error: 'Name is required.' }
  if (name.length > 80) return { ok: false, error: 'Name must be 80 characters or fewer.' }

  if (input.brokerType !== 'alpaca' && input.brokerType !== 'interactive_brokers') {
    return { ok: false, error: 'Unsupported broker type.' }
  }
  if (input.environment !== 'paper' && input.environment !== 'live') {
    return { ok: false, error: 'Invalid environment.' }
  }
  if (!['quality', 'speculative', 'mixed'].includes(input.department)) {
    return { ok: false, error: 'Invalid department.' }
  }

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === input.portfolioSlug)
  if (!portfolio) return { ok: false, error: 'Portfolio not found.' }
  if (portfolio.role !== 'owner' && portfolio.role !== 'admin') {
    return { ok: false, error: 'You need admin access on this portfolio to add a broker account.' }
  }

  const data: Record<string, unknown> = {
    portfolio: portfolio.id,
    name,
    brokerType: input.brokerType,
    environment: input.environment,
    department: input.department,
    isActive: true,
  }

  if (input.brokerType === 'alpaca') {
    const apiKey = trim(input.apiKeyPlaintext)
    const secretKey = trim(input.secretKeyPlaintext)
    if (!apiKey) return { ok: false, error: 'API Key is required for Alpaca.' }
    if (!secretKey) return { ok: false, error: 'Secret Key is required for Alpaca.' }
    data.apiKeyPlaintext = apiKey
    data.secretKeyPlaintext = secretKey
    const baseUrl = trim(input.alpacaBaseUrl)
    if (baseUrl) data.alpacaBaseUrl = baseUrl
  }

  if (input.brokerType === 'interactive_brokers') {
    const accountId = trim(input.ibAccountId)
    if (!accountId) return { ok: false, error: 'IB Account ID is required.' }
    data.ibAccountId = accountId
    const host = trim(input.ibHost)
    if (host) data.ibHost = host
    if (typeof input.ibPort === 'number' && Number.isFinite(input.ibPort)) data.ibPort = input.ibPort
    if (typeof input.ibClientId === 'number' && Number.isFinite(input.ibClientId)) {
      data.ibClientId = input.ibClientId
    }
  }

  const payload = await getPayload({ config: configPromise })

  try {
    const created = await payload.create({
      collection: 'broker-accounts',
      data: data as unknown as RequiredDataFromCollectionSlug<'broker-accounts'>,
      user,
      overrideAccess: false,
    })
    revalidatePath(`/portafolio/${input.portfolioSlug}/brokers`)
    return { ok: true, id: created.id }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create broker account.'
    return { ok: false, error: message }
  }
}
