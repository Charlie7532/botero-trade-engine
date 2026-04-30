/**
 * Seed Instruments — Load seed-data.json into PostgreSQL via Payload Local API.
 *
 * Usage:
 *   pnpm exec tsx src/scripts/seed-instruments.ts
 *
 * Uses Payload Local API (no authentication required, runs server-side).
 */
import 'dotenv/config'
import { getPayload } from 'payload'
import config from '../payload.config'
import seedData from '../collections/Instruments/seed-data.json'

async function seed() {
  console.log('🌱 Starting instrument seed...')
  console.log(`   ${seedData.length} instruments to load`)

  const payload = await getPayload({ config })

  // Check existing count
  const existing = await payload.count({ collection: 'instruments' })
  if (existing.totalDocs > 0) {
    console.log(`⚠️  Already ${existing.totalDocs} instruments in DB. Skipping seed.`)
    console.log('   To re-seed, delete all instruments first.')
    process.exit(0)
  }

  let success = 0
  let failed = 0

  // First pass: create all ETFs and index instruments (they have no sectorETF FK)
  const etfsAndIndex = seedData.filter(
    (i: any) => i.instrumentType !== 'stock'
  )
  const stocks = seedData.filter(
    (i: any) => i.instrumentType === 'stock'
  )

  console.log(`\n📊 Phase 1: Loading ${etfsAndIndex.length} ETFs and indices...`)

  // Map ticker → Payload ID for FK resolution
  const tickerToId: Record<string, string> = {}

  for (const item of etfsAndIndex) {
    try {
      const doc = await (payload.create as Function)({
        collection: 'instruments',
        data: {
          ticker: item.ticker,
          name: item.name,
          instrumentType: item.instrumentType as 'stock' | 'etf_sector' | 'etf_international' | 'etf_commodity' | 'index' | undefined,
          gicsSector: (item.gicsSector || undefined) as 'information_technology' | 'health_care' | 'financials' | 'consumer_discretionary' | 'consumer_staples' | 'industrials' | 'energy' | 'utilities' | 'real_estate' | 'materials' | 'communication_services' | null | undefined,
          universe: item.universe as 'sp500' | 'domestic_sector' | 'international' | 'commodity' | 'guru_gem' | null | undefined,
          cyclicalType: (item.cyclicalType || undefined) as 'cyclical' | 'defensive' | 'mixed' | null | undefined,
          isActive: item.isActive,
          isInSP500: item.isInSP500,
        },
      })
      tickerToId[item.ticker] = doc.id as string
      success++
    } catch (e: any) {
      console.error(`  ❌ ${item.ticker}: ${e.message}`)
      failed++
    }
  }
  console.log(`  ✅ ${success} ETFs/indices loaded`)

  // Phase 2: Load stocks with sectorETF FK resolved
  console.log(`\n📊 Phase 2: Loading ${stocks.length} S&P 500 stocks...`)

  for (let i = 0; i < stocks.length; i++) {
    const item = stocks[i] as any
    try {
      const sectorETFId = item.sectorETFTicker
        ? tickerToId[item.sectorETFTicker]
        : undefined

      await (payload.create as Function)({
        collection: 'instruments',
        data: {
          ticker: item.ticker,
          name: item.name,
          instrumentType: item.instrumentType as 'stock' | undefined,
          gicsSector: (item.gicsSector || undefined) as string | undefined,
          gicsIndustry: item.gicsIndustry || undefined,
          universe: item.universe as 'sp500' | undefined,
          cyclicalType: (item.cyclicalType || undefined) as 'cyclical' | 'defensive' | 'mixed' | undefined,
          marketCap: item.marketCap || undefined,
          isActive: item.isActive,
          isInSP500: item.isInSP500,
          sectorETF: sectorETFId,
        },
      })
      success++

      if ((i + 1) % 50 === 0) {
        console.log(`  📊 Progress: ${i + 1}/${stocks.length}`)
      }
    } catch (e: any) {
      console.error(`  ❌ ${item.ticker}: ${e.message}`)
      failed++
    }
  }

  console.log(`\n${'='.repeat(60)}`)
  console.log(`✅ Seed complete: ${success} success, ${failed} failed`)
  console.log(`   Total in DB: ${success}`)

  process.exit(0)
}

seed().catch((e) => {
  console.error('Seed failed:', e)
  process.exit(1)
})
