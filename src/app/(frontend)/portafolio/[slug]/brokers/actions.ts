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
  // Interactive Brokers — OAuth 1.0a Extended (First Party). See
  // ib_adapter.py's module docstring for what each of these is and how
  // they're generated in IB's OAuth self-service portal.
  ibAccountId?: string
  ibConsumerKeyPlaintext?: string
  ibAccessTokenPlaintext?: string
  ibAccessTokenSecretPlaintext?: string
  ibDhPrime?: string
  ibSignatureKeyPemPlaintext?: string
  ibEncryptionKeyPemPlaintext?: string
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
    const consumerKey = trim(input.ibConsumerKeyPlaintext)
    const accessToken = trim(input.ibAccessTokenPlaintext)
    const accessTokenSecret = trim(input.ibAccessTokenSecretPlaintext)
    const dhPrime = trim(input.ibDhPrime)
    const signatureKeyPem = trim(input.ibSignatureKeyPemPlaintext)
    const encryptionKeyPem = trim(input.ibEncryptionKeyPemPlaintext)

    if (!accountId) return { ok: false, error: 'IB Account ID is required.' }
    if (!consumerKey) return { ok: false, error: 'Consumer Key is required for Interactive Brokers.' }
    if (!accessToken) return { ok: false, error: 'Access Token is required for Interactive Brokers.' }
    if (!accessTokenSecret) return { ok: false, error: 'Access Token Secret is required for Interactive Brokers.' }
    if (!dhPrime) return { ok: false, error: 'Diffie-Hellman prime is required for Interactive Brokers.' }
    if (!signatureKeyPem) return { ok: false, error: 'RSA signature private key is required for Interactive Brokers.' }
    if (!encryptionKeyPem) return { ok: false, error: 'RSA encryption private key is required for Interactive Brokers.' }

    data.ibAccountId = accountId
    data.ibConsumerKeyPlaintext = consumerKey
    data.ibAccessTokenPlaintext = accessToken
    data.ibAccessTokenSecretPlaintext = accessTokenSecret
    data.ibDhPrime = dhPrime
    data.ibSignatureKeyPemPlaintext = signatureKeyPem
    data.ibEncryptionKeyPemPlaintext = encryptionKeyPem
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
