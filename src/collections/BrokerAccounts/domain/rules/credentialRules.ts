import {
  ALPACA_BASE_URLS,
  IB_DEFAULT_HOST,
  IB_DEFAULT_PORT_LIVE,
  IB_DEFAULT_PORT_PAPER,
} from './portfolioRules'

export type BrokerType = 'alpaca' | 'interactive_brokers'

export const BROKER_CREDENTIAL_PROFILES: Record<BrokerType, { coreFields: string[]; advancedFields: string[] }> = {
  alpaca: {
    coreFields: ['apiKeyPlaintext', 'apiKeyMasked', 'secretKeyPlaintext', 'secretKeyMasked'],
    advancedFields: ['alpacaBaseUrl'],
  },
  interactive_brokers: {
    coreFields: ['ibAccountId'],
    advancedFields: ['ibHost', 'ibPort', 'ibClientId'],
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
  'ibHost',
  'ibPort',
  'ibAccountId',
  'ibClientId',
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

  return {
    ibHost: IB_DEFAULT_HOST,
    ibPort: environment === 'live' ? IB_DEFAULT_PORT_LIVE : IB_DEFAULT_PORT_PAPER,
    ibClientId: 1,
  }
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
