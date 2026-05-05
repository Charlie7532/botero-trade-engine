import type { Field } from 'payload'

import { SKILL_TYPES, SKILL_CATEGORIES } from './domain/rules/skillRules'

export const agentSkillsFields: Field[] = [
  {
    name: 'name',
    type: 'text',
    required: true,
    unique: true,
    admin: {
      description: 'Skill name (e.g., "Fundamental Analyst", "Web Search").',
    },
  },
  {
    name: 'slug',
    type: 'text',
    unique: true,
    index: true,
    admin: {
      readOnly: true,
      description: 'Auto-generated identifier.',
    },
  },
  {
    name: 'description',
    type: 'textarea',
    admin: {
      description: 'What capability does this skill give the agent?',
    },
  },
  {
    name: 'type',
    type: 'select',
    required: true,
    defaultValue: 'custom',
    options: [...SKILL_TYPES],
    admin: {
      description: 'Built-in: Anthropic-provided skill. Custom: prompt injected into system prompt.',
    },
  },
  {
    name: 'category',
    type: 'select',
    required: true,
    options: [...SKILL_CATEGORIES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'isActive',
    type: 'checkbox',
    defaultValue: true,
    admin: {
      position: 'sidebar',
    },
  },
  // For built-in skills: the Anthropic skill identifier
  {
    name: 'builtinId',
    type: 'text',
    admin: {
      description: 'Anthropic skill ID (e.g., "web_search"). Only for built-in type.',
      condition: (data) => data?.type === 'builtin',
    },
  },
  // For custom skills: the prompt content that gets injected
  {
    name: 'promptContent',
    type: 'code',
    admin: {
      language: 'markdown',
      description: 'Skill instructions injected into the agent system prompt.',
      condition: (data) => data?.type === 'custom',
    },
  },
]
