export const MCP_SERVER_TYPES = [
  { label: 'URL (Remote)', value: 'url' },
  { label: 'Stdio (Local)', value: 'stdio' },
] as const

export type McpServerType = 'url' | 'stdio'

// Credential scope – platform = shared, portfolio = per‑portfolio credentials
export const MCP_CREDENTIAL_SCOPES = [
  { label: 'Platform (shared)', value: 'platform' },
  { label: 'Portfolio (per‑portfolio)', value: 'portfolio' },
] as const

export type McpCredentialScope = 'platform' | 'portfolio'

export const MCP_CATEGORIES = [
  // Broker category removed – broker MCPs are derived from BrokerAccount
  { label: 'Market Data', value: 'data' },
  { label: 'Analytics', value: 'analytics' },
  { label: 'Macro', value: 'macro' },
  { label: 'News', value: 'news' },
] as const

export type McpCategory = 'data' | 'analytics' | 'macro' | 'news'

export const PERMISSION_POLICIES = [
  { label: 'Always Allow', value: 'always_allow' },
  { label: 'Ask User', value: 'ask_user' },
] as const

export type PermissionPolicy = 'always_allow' | 'ask_user'

/**
 * Helper to decide the default credential scope based on category.
 * All non‑broker categories default to “platform”.
 */
export function defaultCredentialScope(category: McpCategory): McpCredentialScope {
  return 'platform'
}
