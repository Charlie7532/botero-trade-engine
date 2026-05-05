import type { Field } from 'payload'

export const projectVaultsFields: Field[] = [
  {
    name: 'name',
    type: 'text',
    required: true,
    unique: true,
    admin: { description: 'Human‑readable vault identifier (e.g., "Platform MCP Vault").' },
  },
  {
    name: 'vaultId',
    type: 'text',
    required: true,
    admin: { description: 'External vault ID returned by the provider.', readOnly: true },
  },
  {
    name: 'status',
    type: 'select',
    defaultValue: 'pending',
    options: [
      { label: 'Pending', value: 'pending' },
      { label: 'Ready', value: 'ready' },
      { label: 'Error', value: 'error' },
    ],
    admin: { description: 'Current sync status.' },
  },
  {
    name: 'lastSyncedAt',
    type: 'date',
    admin: { description: 'When the vault was last successfully updated.' },
  },
]
