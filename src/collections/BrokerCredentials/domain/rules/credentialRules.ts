export const ALPACA_SECRET_KEYS = ['apiKey', 'secretKey'] as const
export const IB_SECRET_KEYS = ['apiKey'] as const

export const ALL_CREDENTIAL_KEY_OPTIONS = [
  { label: 'API Key', value: 'apiKey' },
  { label: 'Secret Key', value: 'secretKey' },
] as const

export function maskCredentialValue(value: string): string {
  if (!value || value.length <= 4) return '••••••••'
  return `••••${value.slice(-4)}`
}

export function isPlaintextValue(value: string): boolean {
  try {
    const decoded = Buffer.from(value, 'base64')
    return decoded.toString('base64') !== value
  } catch {
    return true
  }
}
