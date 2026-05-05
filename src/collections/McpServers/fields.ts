import type { Field } from 'payload'

import {
  MCP_SERVER_TYPES,
  MCP_CATEGORIES,
  PERMISSION_POLICIES,
} from './domain/rules/mcpRules'

export const mcpServersFields: Field[] = [
  {
    name: 'name',
    type: 'text',
    required: true,
    unique: true,
    admin: {
      description: 'Display name (e.g., "Alpaca Trading", "Yahoo Finance").',
    },
  },
  {
    name: 'slug',
    type: 'text',
    unique: true,
    index: true,
    admin: {
      readOnly: true,
      description: 'Auto-generated identifier used in agent configs.',
    },
  },
  {
    name: 'description',
    type: 'textarea',
    admin: {
      description: 'What capabilities does this MCP provide?',
    },
  },
  {
    name: 'type',
    type: 'select',
    required: true,
    defaultValue: 'url',
    options: [...MCP_SERVER_TYPES],
    admin: {
      description: 'Only "URL" works with Claude Cloud agents.',
    },
  },
  {
    name: 'url',
    type: 'text',
    admin: {
      description: 'Remote MCP endpoint (e.g., https://mcp.example.com/mcp).',
      condition: (data) => data?.type === 'url',
    },
  },
  {
    name: 'category',
    type: 'select',
    required: true,
    options: [...MCP_CATEGORIES],
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
      description: 'Disable to prevent agents from using this MCP.',
    },
  },
  {
    name: 'defaultPermissionPolicy',
    type: 'select',
    defaultValue: 'always_allow',
    options: [...PERMISSION_POLICIES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'credentialScope',
    type: 'select',
    required: true,
    defaultValue: 'platform',
    options: [
      { label: 'Platform (shared)', value: 'platform' },
      { label: 'Portfolio (per-portfolio)', value: 'portfolio' },
    ],
    admin: {
      description: 'Scope of credentials – shared platform or per-portfolio.',
    },
  },
  {
    name: 'platformApiKeyEnvVar',
    type: 'text',
    admin: {
      description: 'Env var name that stores the API key for platform-wide MCPs.',
    },
  },
  {
    name: 'linkedBrokerType',
    type: 'text',
    admin: {
      description: 'Broker type this MCP is linked to (e.g., alpaca). Leave empty for generic MCPs.',
    },
  },
  // Sync tracking fields (populated by cascade hooks)
  {
    name: 'lastSyncedAt',
    type: 'date',
    admin: {
      readOnly: true,
      position: 'sidebar',
      description: 'Last time dependent bots were resynced.',
    },
  },
  {
    name: 'syncedBotCount',
    type: 'number',
    admin: {
      readOnly: true,
      position: 'sidebar',
      description: 'Number of bots resynced on last change.',
    },
  },
]
