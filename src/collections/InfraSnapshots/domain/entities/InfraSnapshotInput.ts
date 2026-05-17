/** Pure shape produced by probes and persisted as one InfraSnapshot row. */
export interface InfraSnapshotInput {
  capturedAt: string

  // Neon project counters (cumulative)
  cpuUsedSec?: number
  computeTimeSec?: number
  activeTimeSec?: number
  workingDataBytes?: number
  dataStorageBytesHour?: number
  writtenDataBytes?: number
  dataTransferBytes?: number

  // Neon endpoint state
  endpointState?: string
  autoscaleMinCu?: number
  autoscaleMaxCu?: number

  // Postgres connections
  activeBackends?: number
  idleBackends?: number
  idleInTxnBackends?: number
  totalBackends?: number
  maxConnections?: number

  // Postgres cumulative counters
  xactCommit?: number
  xactRollback?: number
  deadlocks?: number
  blksHit?: number
  blksRead?: number

  // PgBouncer pooler stats (Neon does not expose admin console — left undefined)
  poolerActive?: number
  poolerWaiting?: number
  poolerServerActive?: number
  poolerServerIdle?: number

  errors?: string
}

export interface NeonReading {
  cpuUsedSec?: number
  computeTimeSec?: number
  activeTimeSec?: number
  workingDataBytes?: number
  dataStorageBytesHour?: number
  writtenDataBytes?: number
  dataTransferBytes?: number
  endpointState?: string
  autoscaleMinCu?: number
  autoscaleMaxCu?: number
  error?: string
}

export interface PgReading {
  activeBackends?: number
  idleBackends?: number
  idleInTxnBackends?: number
  totalBackends?: number
  maxConnections?: number
  xactCommit?: number
  xactRollback?: number
  deadlocks?: number
  blksHit?: number
  blksRead?: number
  error?: string
}

export interface PoolerReading {
  poolerActive?: number
  poolerWaiting?: number
  poolerServerActive?: number
  poolerServerIdle?: number
  error?: string
}
