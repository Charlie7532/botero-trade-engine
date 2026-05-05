export const SKILL_TYPES = [
  { label: 'Built-in (Anthropic)', value: 'builtin' },
  { label: 'Custom (Prompt-based)', value: 'custom' },
] as const

export type SkillType = 'builtin' | 'custom'

export const SKILL_CATEGORIES = [
  { label: 'Analysis', value: 'analysis' },
  { label: 'Execution', value: 'execution' },
  { label: 'Risk', value: 'risk' },
  { label: 'Research', value: 'research' },
  { label: 'General', value: 'general' },
] as const

export type SkillCategory = 'analysis' | 'execution' | 'risk' | 'research' | 'general'
