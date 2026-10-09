import { ALPACA_BASE_URLS } from './portfolioRules'

export type BrokerType = 'alpaca' | 'interactive_brokers'

export const BROKER_CREDENTIAL_PROFILES: Record<BrokerType, { coreFields: string[]; advancedFields: string[] }> = {
  alpaca: {
    coreFields: ['apiKeyPlaintext', 'apiKeyMasked', 'secretKeyPlaintext', 'secretKeyMasked'],
    advancedFields: ['alpacaBaseUrl'],
  },
  interactive_brokers: {
    // OAuth 1.0a Extended (First Party) fields — see ib_adapter.py's module
    // docstring. ibAccountId is which IB account to trade, unrelated to
    // auth. ibDhPrime is a public Diffie-Hellman parameter (not a secret on
    // its own), so it isn't in the encrypted set below.
    coreFields: [
      'ibAccountId',
      'ibConsumerKeyPlaintext',
      'ibConsumerKeyMasked',
      'ibAccessTokenPlaintext',
      'ibAccessTokenMasked',
      'ibAccessTokenSecretPlaintext',
      'ibAccessTokenSecretMasked',
    ],
    advancedFields: ['ibDhPrime', 'ibSignatureKeyPemPlaintext', 'ibEncryptionKeyPemPlaintext'],
  },
}

export function resolveBrokerTypeFromCredentialData(data: Record<string, any>): BrokerType | null {
  const directBroker = data?.brokerType
  if (directBroker === 'alpaca' || directBroker === 'interactive_brokers') {
    return directBroker
  }

  return null
}

export const EDITABLE_CREDENTIAL_FIELDS = [
  'portfolio',
  'brokerType',
  'environment',
  'apiKeyPlaintext',
  'secretKeyPlaintext',
  'alpacaBaseUrl',
  'ibAccountId',
  'ibConsumerKeyPlaintext',
  'ibAccessTokenPlaintext',
  'ibAccessTokenSecretPlaintext',
  'ibDhPrime',
  'ibSignatureKeyPemPlaintext',
  'ibEncryptionKeyPemPlaintext',
] as const

export function requiresSecretKey(brokerType: BrokerType): boolean {
  return brokerType === 'alpaca'
}

export function defaultConnectionValues(brokerType: BrokerType, environment: 'paper' | 'live') {
  if (brokerType === 'alpaca') {
    return {
      alpacaBaseUrl: environment === 'live' ? ALPACA_BASE_URLS.live : ALPACA_BASE_URLS.paper,
    }
  }

  // IB's OAuth credentials have no sensible defaults — every field is
  // specific to the account that registered it in IB's portal.
  return {}
}

export function maskCredentialValue(value: string): string {
  if (!value || value.length <= 4) return '*****'
  return `*****${value.slice(-4)}`
}

export function isPlaintextValue(value: string): boolean {
  try {
    const decoded = Buffer.from(value, 'base64')
    return decoded.toString('base64') !== value
  } catch {
    return true
  }
}
