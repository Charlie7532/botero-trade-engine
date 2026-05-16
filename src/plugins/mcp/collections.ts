import type { MCPPluginConfig } from '@payloadcms/plugin-mcp'

import {
  buildSensitiveFieldStripper,
  BROKER_ACCOUNT_SENSITIVE_FIELDS,
  MCP_SERVER_SENSITIVE_FIELDS,
  PROJECT_VAULT_SENSITIVE_FIELDS,
  USER_SENSITIVE_FIELDS,
} from './sanitizers'

/**
 * Collections exposed via the Payload MCP plugin.
 *
 * Guidelines:
 *  - Only enable collections that an agent has a real reason to read.
 *  - Default to `find` only. Enable `create`/`update`/`delete` deliberately.
 *  - For collections that may include secrets or PII, attach an
 *    `overrideResponse` built with `buildSensitiveFieldStripper`.
 *  - Do NOT enable: `user-avatar` (binary media), `payload-mcp-api-keys`
 *    (auth state), or anything else holding raw credentials.
 */
export const mcpCollections: NonNullable<MCPPluginConfig['collections']> = {
  // ── Portfolio operations ────────────────────────────────────────────────
  portfolios: {
    enabled: { find: true, create: true, update: true },
    description:
      'Trading portfolios owned by users. Each portfolio aggregates broker accounts, bots, and trade history.',
  },
  'portfolio-memberships': {
    enabled: { find: true, create: true, update: true, delete: true },
    description:
      'Membership and role assignments mapping users to portfolios (owner, admin, viewer).',
  },

  // ── Bots & assignments ──────────────────────────────────────────────────
  bots: {
    enabled: { find: true, create: true, update: true },
    description:
      'Algorithmic trading bots (Quality, Speculative, custom). Each bot wraps a strategy and risk profile.',
  },
  'bot-assignments': {
    enabled: { find: true, create: true, update: true, delete: true },
    description: 'Assignments binding bots to portfolios and broker accounts for execution.',
  },

  // ── Agent skills & MCP servers (sanitized) ──────────────────────────────
  'agent-skills': {
    enabled: { find: true, create: true, update: true },
    description:
      'Reusable agent skills registry. Each skill describes a capability an LLM agent can invoke against the trading engine.',
  },
  'mcp-servers': {
    enabled: { find: true },
    description:
      'Registered MCP servers (Finnhub, Alpaca, Unusual Whales, FRED, GuruFocus, etc.). Connection URLs and credentials are stripped from responses.',
    overrideResponse: buildSensitiveFieldStripper(MCP_SERVER_SENSITIVE_FIELDS),
  },

  // ── Market & strategy reference data ────────────────────────────────────
  instruments: {
    enabled: { find: true, create: true, update: true },
    description: 'Tradable instruments (equities, ETFs, options underlyings) with metadata and tags.',
  },
  'regime-phases': {
    enabled: { find: true, create: true, update: true },
    description:
      'Volatility/regime phase classifications produced by the vol-regime-intelligence module.',
  },
  'calibration-profiles': {
    enabled: { find: true, create: true, update: true },
    description:
      'Calibration profiles for strategies and risk managers (Quality/Speculative parameter sets).',
  },
  'candidate-screenings': {
    enabled: { find: true, create: true, update: true },
    description:
      'Research & Intelligence candidate screenings for Quality and Speculative tracks.',
  },
  'trade-snapshots': {
    enabled: { find: true, create: true },
    description:
      'Point-in-time trade snapshots (entry/exit context, signals, regime, gamma, flow). Used by the autopsy/forensics pipeline.',
  },

  // ── Vaults & secrets (sanitized) ────────────────────────────────────────
  'project-vaults': {
    enabled: { find: true },
    description:
      'Project secrets vault metadata (names and labels only). Secret values are stripped from responses.',
    overrideResponse: buildSensitiveFieldStripper(PROJECT_VAULT_SENSITIVE_FIELDS),
  },

  // ── Broker accounts (sanitized) ─────────────────────────────────────────
  'broker-accounts': {
    enabled: { find: true },
    description:
      'Connected broker accounts (Alpaca, Interactive Brokers, etc.). API keys, secrets, and tokens are stripped from responses.',
    overrideResponse: buildSensitiveFieldStripper(BROKER_ACCOUNT_SENSITIVE_FIELDS),
  },

  // ── Media (read-only) ───────────────────────────────────────────────────
  media: {
    enabled: { find: true },
    description: 'Public media library metadata (images and files).',
  },

  // ── Users (read-only, sanitized) ────────────────────────────────────────
  users: {
    enabled: { find: true },
    description:
      'Application users (read-only). Look up by id or email via standard find filters. Auth fields and OAuth identifiers are stripped from responses.',
    overrideResponse: buildSensitiveFieldStripper(USER_SENSITIVE_FIELDS),
  },
}
