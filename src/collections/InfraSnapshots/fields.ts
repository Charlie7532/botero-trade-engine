import type { Field } from 'payload'

export const infraSnapshotsFields: Field[] = [
  {
    name: 'capturedAt',
    type: 'date',
    required: true,
    index: true,
    admin: {
      date: { pickerAppearance: 'dayAndTime', displayFormat: 'yyyy-MM-dd HH:mm' },
      description: 'When this snapshot was captured (UTC)',
    },
  },

  // ─── Neon project counters (cumulative for billing period) ──
  {
    type: 'row',
    fields: [
      {
        name: 'cpuUsedSec',
        type: 'number',
        admin: { description: 'Cumulative cpu_used_sec from Neon API' },
      },
      {
        name: 'computeTimeSec',
        type: 'number',
        admin: { description: 'Cumulative compute_time_seconds' },
      },
      {
        name: 'activeTimeSec',
        type: 'number',
        admin: { description: 'Cumulative active_time_seconds' },
      },
    ],
  },
  {
    type: 'row',
    fields: [
      { name: 'workingDataBytes', type: 'number', admin: { description: 'Cache footprint (proxy for RAM)' } },
      { name: 'dataStorageBytesHour', type: 'number' },
      { name: 'writtenDataBytes', type: 'number' },
      { name: 'dataTransferBytes', type: 'number' },
    ],
  },

  // ─── Neon endpoint state ────────────────────────────────────
  {
    type: 'row',
    fields: [
      { name: 'endpointState', type: 'text', admin: { description: 'idle | active | starting | etc.' } },
      { name: 'autoscaleMinCu', type: 'number' },
      { name: 'autoscaleMaxCu', type: 'number' },
    ],
  },

  // ─── Postgres connections (pg_stat_activity / pg_stat_database) ─
  {
    type: 'row',
    fields: [
      { name: 'activeBackends', type: 'number' },
      { name: 'idleBackends', type: 'number' },
      { name: 'idleInTxnBackends', type: 'number' },
      { name: 'totalBackends', type: 'number' },
      { name: 'maxConnections', type: 'number' },
    ],
  },

  // ─── Postgres cumulative counters (for delta-rate widgets) ──
  {
    type: 'row',
    fields: [
      { name: 'xactCommit', type: 'number' },
      { name: 'xactRollback', type: 'number' },
      { name: 'deadlocks', type: 'number' },
      { name: 'blksHit', type: 'number' },
      { name: 'blksRead', type: 'number' },
    ],
  },

  // ─── PgBouncer pooler stats (nullable — Neon may not expose) ─
  {
    type: 'row',
    fields: [
      { name: 'poolerActive', type: 'number', admin: { description: 'Active client connections' } },
      { name: 'poolerWaiting', type: 'number', admin: { description: 'Waiting client connections' } },
      { name: 'poolerServerActive', type: 'number' },
      { name: 'poolerServerIdle', type: 'number' },
    ],
  },

  {
    name: 'errors',
    type: 'text',
    admin: { description: 'Comma-separated source identifiers that failed during this capture' },
  },
]
