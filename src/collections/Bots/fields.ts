import type { Field } from 'payload'

import {
  BOT_STATUSES,
  STRATEGY_TYPES,
  EXECUTION_TYPES,
  CLAUDE_MODELS,
  AGENT_SYNC_STATUSES,
} from './domain/rules/botRules'

const isAgent = (data: any) => data?.executionType === 'agent'

export const botsFields: Field[] = [
  {
    name: 'name',
    type: 'text',
    required: true,
  },
  {
    name: 'portfolio',
    type: 'relationship',
    relationTo: 'portfolios',
    required: true,
    index: true,
  },
  {
    name: 'executionType',
    type: 'select',
    required: true,
    defaultValue: 'agent',
    options: [...EXECUTION_TYPES],
    admin: {
      description: 'AI Agent = Claude-powered. Strategy = traditional algorithm running in the Python backend.',
    },
  },
  {
    name: 'strategyType',
    type: 'select',
    required: true,
    options: [...STRATEGY_TYPES],
  },
  {
    name: 'status',
    type: 'select',
    required: true,
    defaultValue: 'stopped',
    options: [...BOT_STATUSES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'description',
    type: 'textarea',
  },
  {
    name: 'config',
    type: 'json',
    admin: {
      description: 'Strategy-specific configuration (parameters, thresholds, filters).',
    },
  },
  // ─── Claude Managed Agent Identity (sidebar, read-only, agent only) ────
  {
    name: 'agentId',
    type: 'text',
    admin: {
      readOnly: true,
      position: 'sidebar',
      description: 'Claude Agent ID (auto-synced on save).',
      condition: isAgent,
    },
  },
  {
    name: 'agentVersion',
    type: 'number',
    admin: {
      readOnly: true,
      position: 'sidebar',
      description: 'Current agent version in Anthropic.',
      condition: isAgent,
    },
  },
  {
    name: 'agentSyncStatus',
    type: 'select',
    defaultValue: 'not_created',
    options: [...AGENT_SYNC_STATUSES],
    admin: {
      readOnly: true,
      position: 'sidebar',
      condition: isAgent,
    },
  },
  {
    name: 'agentSyncError',
    type: 'text',
    admin: {
      readOnly: true,
      position: 'sidebar',
      condition: (data) => isAgent(data) && data?.agentSyncStatus === 'error',
    },
  },
  // ─── Tabs ─────────────────────────────────────────────────────────────
  {
    type: 'tabs',
    tabs: [
      {
        label: 'Claude Agent',
        admin: {
          condition: isAgent,
        },
        fields: [
          {
            name: 'model',
            type: 'select',
            defaultValue: 'claude-sonnet-4-6',
            options: [...CLAUDE_MODELS],
            admin: {
              description: 'Which Claude model powers this agent.',
            },
          },
          {
            name: 'systemPrompt',
            type: 'code',
            admin: {
              language: 'markdown',
              description: 'The system prompt that defines this agent\'s behavior and expertise.',
            },
          },
          {
            name: 'mcpServers',
            type: 'relationship',
            relationTo: 'mcp-servers',
            hasMany: true,
            admin: {
              description: 'Select which MCP servers this agent can access.',
            },
          },
          {
            name: 'skills',
            type: 'relationship',
            relationTo: 'agent-skills',
            hasMany: true,
            admin: {
              description: 'Select which skills this agent has.',
            },
          },
          {
            name: 'agentMetadata',
            type: 'json',
            admin: {
              description: 'Arbitrary metadata stored on the Claude agent.',
            },
          },
        ],
      },
      {
        label: 'Broker Account Assignments',
        fields: [
          {
            name: 'assignments',
            type: 'join',
            collection: 'bot-assignments',
            on: 'bot',
          },
        ],
      },
    ],
  },
]
