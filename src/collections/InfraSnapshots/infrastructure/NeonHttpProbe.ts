import type { NeonReading } from '../domain/entities/InfraSnapshotInput'
import type { NeonProbe } from '../domain/ports/InfraProbes'

const NEON_BASE = 'https://console.neon.tech/api/v2'

function n(v: unknown): number | undefined {
  if (v === null || v === undefined) return undefined
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'bigint') return Number(v)
  if (typeof v === 'string') {
    const p = Number(v)
    return Number.isFinite(p) ? p : undefined
  }
  return undefined
}

/**
 * Fetches project + endpoint summary from the Neon Console REST API.
 * Only fields exposed by the public v2 API are read — there is no time-series
 * CPU/RAM endpoint (the Console UI uses internal observability services).
 */
export class NeonHttpProbe implements NeonProbe {
  constructor(
    private readonly apiKey = process.env.NEON_API_KEY,
    private readonly projectId = process.env.NEON_PROJECT_ID,
  ) {}

  async read(): Promise<NeonReading> {
    if (!this.apiKey || !this.projectId) return { error: 'env-missing' }

    const headers = { Authorization: `Bearer ${this.apiKey}`, Accept: 'application/json' }
    try {
      const [projRes, epRes] = await Promise.all([
        fetch(`${NEON_BASE}/projects/${this.projectId}`, { headers, cache: 'no-store' }),
        fetch(`${NEON_BASE}/projects/${this.projectId}/endpoints`, { headers, cache: 'no-store' }),
      ])
      if (!projRes.ok || !epRes.ok) {
        return { error: `http-${projRes.status}-${epRes.status}` }
      }
      const projJson = (await projRes.json()) as { project?: Record<string, unknown> }
      const epJson = (await epRes.json()) as { endpoints?: Array<Record<string, unknown>> }
      const p = projJson.project ?? {}
      const ep =
        epJson.endpoints?.find((e) => e.type === 'read_write') ?? epJson.endpoints?.[0] ?? {}
      return {
        cpuUsedSec: n(p.cpu_used_sec),
        computeTimeSec: n(p.compute_time_seconds),
        activeTimeSec: n(p.active_time_seconds),
        workingDataBytes: n(p.working_data_bytes),
        dataStorageBytesHour: n(p.data_storage_bytes_hour),
        writtenDataBytes: n(p.written_data_bytes),
        dataTransferBytes: n(p.data_transfer_bytes),
        endpointState: typeof ep.current_state === 'string' ? ep.current_state : undefined,
        autoscaleMinCu: n(ep.autoscaling_limit_min_cu),
        autoscaleMaxCu: n(ep.autoscaling_limit_max_cu),
      }
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'fetch-failed' }
    }
  }
}
