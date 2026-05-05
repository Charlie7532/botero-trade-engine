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
]
