import type { Endpoint } from 'payload'

import { captureSnapshot } from '../../application/useCases/captureSnapshot'
import { NeonHttpProbe } from '../../infrastructure/NeonHttpProbe'
import { PgStatProbe, PgRetentionSweeper, type PgClient } from '../../infrastructure/PgStatProbe'
import { UnavailablePoolerProbe } from '../../infrastructure/UnavailablePoolerProbe'

/**
 * GET /api/infra-snapshots/capture
 *
 * Triggered by the Vercel cron every 5 min (configured in vercel.json — Vercel
 * cron always uses GET). Authenticated via `Authorization: Bearer <CRON_SECRET>`,
 * which Vercel injects automatically for crons targeting this project.
 *
 * Logged-in admin users are also allowed (for manual runs from the UI).
 */
export const captureSnapshotEndpoint: Endpoint = {
  path: '/capture',
  method: 'get',
  handler: async (req) => {
    const auth = req.headers.get('authorization')
    const isCron = !!process.env.CRON_SECRET && auth === `Bearer ${process.env.CRON_SECRET}`
    if (!isCron && !req.user) {
      return Response.json({ ok: false, error: 'unauthorized' }, { status: 401 })
    }

    const drizzle = (req.payload.db as unknown as { drizzle?: { $client?: PgClient } }).drizzle
    const client = drizzle?.$client
    if (!client || typeof client.query !== 'function') {
      return Response.json({ ok: false, error: 'adapter-offline' }, { status: 500 })
    }

    const result = await captureSnapshot({
      payload: req.payload,
      neon: new NeonHttpProbe(),
      pg: new PgStatProbe(client),
      pooler: new UnavailablePoolerProbe(),
      sweeper: new PgRetentionSweeper(client),
    })

    return Response.json({ ok: true, ...result })
  },
}
