export const EXECUTION_TYPES = [
  { label: 'AI Agent (Claude)', value: 'agent' },
  { label: 'Strategy (Backend)', value: 'strategy' },
] as const

export type ExecutionType = 'agent' | 'strategy'

export const BOT_STATUSES = [
  { label: 'Active', value: 'active' },
  { label: 'Paused', value: 'paused' },
  { label: 'Stopped', value: 'stopped' },
  { label: 'Error', value: 'error' },
] as const

export type BotStatus = 'active' | 'paused' | 'stopped' | 'error'

export const STRATEGY_TYPES = [
  { label: 'QGARP', value: 'qgarp' },
  { label: 'Momentum', value: 'momentum' },
  { label: 'Mean Reversion', value: 'mean_reversion' },
  { label: 'Trend Following', value: 'trend_following' },
  { label: 'Custom', value: 'custom' },
] as const

export type StrategyType = 'qgarp' | 'momentum' | 'mean_reversion' | 'trend_following' | 'custom'

export const CLAUDE_MODELS = [
  { label: 'Claude Opus 4.7', value: 'claude-opus-4-7' },
  { label: 'Claude Sonnet 4.6', value: 'claude-sonnet-4-6' },
  { label: 'Claude Haiku 4', value: 'claude-haiku-4' },
] as const

export type ClaudeModel = 'claude-opus-4-7' | 'claude-sonnet-4-6' | 'claude-haiku-4'

export const AGENT_SYNC_STATUSES = [
  { label: 'Not Created', value: 'not_created' },
  { label: 'Synced', value: 'synced' },
  { label: 'Pending', value: 'pending' },
  { label: 'Error', value: 'error' },
] as const

export type AgentSyncStatus = 'not_created' | 'synced' | 'pending' | 'error'
