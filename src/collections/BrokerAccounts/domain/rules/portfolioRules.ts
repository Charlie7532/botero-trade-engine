export const BROKER_TYPES = [
  { label: 'Alpaca', value: 'alpaca' },
  { label: 'Interactive Brokers', value: 'interactive_brokers' },
] as const

export type BrokerType = 'alpaca' | 'interactive_brokers'

export const ENVIRONMENTS = [
  { label: 'Paper', value: 'paper' },
  { label: 'Live', value: 'live' },
] as const

export type PortfolioEnvironment = 'paper' | 'live'

export function requiredCredentialKeys(brokerType: BrokerType): string[] {
  switch (brokerType) {
    case 'alpaca':
      return ['apiKey', 'secretKey']
    case 'interactive_brokers':
      return ['apiKey']
    default:
      return []
  }
}

export const ALPACA_BASE_URLS = {
  paper: 'https://paper-api.alpaca.markets',
  live: 'https://api.alpaca.markets',
} as const

export const IB_DEFAULT_HOST = '127.0.0.1'
export const IB_DEFAULT_PORT_PAPER = 7497
export const IB_DEFAULT_PORT_LIVE = 7496
