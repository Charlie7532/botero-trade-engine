/**
 * Reset Dashboard Layout — Delete all users' saved `dashboard-layout` preferences.
 *
 * Why: Payload persists the widget config snapshot (including `minWidth`/`maxWidth`)
 * into each user's saved layout. After widening a widget's allowed widths in
 * `src/widgets/index.ts`, existing users still see the OLD width dropdown options
 * until their saved preference is cleared.
 *
 * Usage:
 *   pnpm exec tsx src/scripts/reset-dashboard-layout.ts
 */
import 'dotenv/config'
import { getPayload } from 'payload'
import config from '../payload.config'

async function run() {
  const payload = await getPayload({ config })

  const result = await payload.delete({
    collection: 'payload-preferences',
    where: { key: { equals: 'dashboard-layout' } },
  })

  const count = Array.isArray(result?.docs) ? result.docs.length : 0
  console.log(`✅ Deleted ${count} dashboard-layout preference(s).`)
  console.log('   Reload the admin dashboard — widget widths now reflect current config.')
  process.exit(0)
}

run().catch((err) => {
  console.error('❌ Reset failed:', err)
  process.exit(1)
})
