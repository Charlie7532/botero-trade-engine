export const MCP_SERVER_TYPES = [
  { label: 'URL (Remote)', value: 'url' },
  { label: 'Stdio (Local)', value: 'stdio' },
] as const

export type McpServerType = 'url' | 'stdio'

export const MCP_CATEGORIES = [
  { label: 'Broker', value: 'broker' },
  { label: 'Market Data', value: 'data' },
  { label: 'Analytics', value: 'analytics' },
  { label: 'Macro', value: 'macro' },
  { label: 'News', value: 'news' },
] as const

export type McpCategory = 'broker' | 'data' | 'analytics' | 'macro' | 'news'

export const PERMISSION_POLICIES = [
  { label: 'Always Allow', value: 'always_allow' },
  { label: 'Ask User', value: 'ask_user' },
] as const

export type PermissionPolicy = 'always_allow' | 'ask_user'
