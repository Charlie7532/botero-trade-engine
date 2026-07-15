/**
 * Strip sensitive keys from arbitrarily nested data and return a transformed
 * MCP `overrideResponse` payload. Use this for collections whose documents
 * may include auth fields, secrets, or other PII the agent should never see.
 */

type McpResponse = {
  content: Array<{
    text: string
    type: string
  }>
}

export function buildSensitiveFieldStripper(sensitiveKeys: Iterable<string>) {
  const denylist = new Set(sensitiveKeys)

  const sanitize = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(sanitize)
    if (value && typeof value === 'object') {
      const out: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        if (denylist.has(k)) continue
        out[k] = sanitize(v)
      }
      return out
    }
    return value
  }

  return (response: McpResponse): McpResponse => ({
    content: response.content.map((item) => {
      if (item.type !== 'text') return item
      try {
        const parsed = JSON.parse(item.text)
        return { ...item, text: JSON.stringify(sanitize(parsed)) }
      } catch {
        return item
      }
    }),
  })
}

/**
 * Default sensitive-field denylist for the `users` collection. Covers Payload
 * auth-managed fields and OAuth identifiers.
 */
export const USER_SENSITIVE_FIELDS = [
  'password',
  'hash',
  'salt',
  'apiKey',
  'apiKeyIndex',
  'enableAPIKey',
  'resetPasswordToken',
  'resetPasswordExpiration',
  'loginAttempts',
  'lockUntil',
  'sessions',
  '_verificationToken',
  'sub',
] as const

/**
 * Sensitive-field denylist for `broker-accounts`. Broker credentials, API
 * keys, and webhook secrets must never reach an MCP client.
 */
export const BROKER_ACCOUNT_SENSITIVE_FIELDS = [
  'apiKey',
  'apiSecret',
  'accessToken',
  'refreshToken',
  'webhookSecret',
  'clientSecret',
  'password',
] as const

/**
 * Sensitive-field denylist for `mcp-servers`. Connection URLs and bearer
 * tokens for upstream MCP servers (Finnhub, Alpaca, Unusual Whales, etc.)
 * must stay server-side.
 */
export const MCP_SERVER_SENSITIVE_FIELDS = [
  'apiKey',
  'apiSecret',
  'accessToken',
  'bearerToken',
  'authToken',
  'connectionUrl',
  'serverUrl',
  'env',
  'environment',
] as const

/**
 * Sensitive-field denylist for `project-vaults`. Vaults hold platform
 * secrets (DB connection strings, MCP server credentials, signing keys).
 */
export const PROJECT_VAULT_SENSITIVE_FIELDS = [
  'value',
  'secret',
  'token',
  'password',
  'key',
  'credentials',
  'env',
] as const
