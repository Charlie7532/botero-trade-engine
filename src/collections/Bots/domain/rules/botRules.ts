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
  // Quality Department (Hohn & Munger — 80%)
  { label: 'Quality: Value', value: 'quality_value' },
  { label: 'Quality: Growth', value: 'quality_growth' },
  { label: 'Quality: Dividend', value: 'quality_dividend' },
  // Speculative Department (Eifert & PTJ — 20%)
  { label: 'Speculative: Momentum', value: 'speculative_momentum' },
  { label: 'Speculative: Gamma', value: 'speculative_gamma' },
  { label: 'Speculative: Breakout', value: 'speculative_breakout' },
  { label: 'Speculative: Spring', value: 'speculative_spring' },
  // Legacy
  { label: 'Custom', value: 'custom' },
] as const

export type StrategyType =
  | 'quality_value'
  | 'quality_growth'
  | 'quality_dividend'
  | 'speculative_momentum'
  | 'speculative_gamma'
  | 'speculative_breakout'
  | 'speculative_spring'
  | 'custom'

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
