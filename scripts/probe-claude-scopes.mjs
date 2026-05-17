import fs from 'node:fs'
const txt = fs.readFileSync('.env.local','utf8') + '\n' + fs.readFileSync('.env','utf8')
const m = txt.match(/^\s*ANTHROPIC_ADMIN_KEY\s*=\s*([^\r\n]+)/m)
const KEY = m[1].replace(/^["']|["']$/g, '')
const H = { 'anthropic-version':'2023-06-01', 'x-api-key': KEY }

const WS = 'wrkspc_01HkPJ9qYoxPjbAifCBLfrAG'
const now = new Date()
const todayUtc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
const tomorrow = new Date(todayUtc.getTime() + 864e5).toISOString()
const sevenAgo = new Date(todayUtc.getTime() - 6*864e5).toISOString()
const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString()

async function fetchCost(from, to, label) {
  const p = new URLSearchParams({ starting_at: from, ending_at: to, bucket_width: '1d', limit: '31' })
  p.append('group_by[]', 'workspace_id')
  const r = await fetch('https://api.anthropic.com/v1/organizations/cost_report?' + p, { headers: H })
  const j = await r.json()
  console.log(`\n=== ${label} ===`)
  let totalAll = 0, totalWs = 0
  for (const b of j.data ?? []) {
    let dayAll = 0, dayWs = 0
    for (const row of b.results ?? []) {
      const amt = Number(row.amount ?? 0)
      dayAll += amt
      if (row.workspace_id === WS) dayWs += amt
    }
    totalAll += dayAll
    totalWs += dayWs
    if (dayAll > 0) console.log(`  ${b.starting_at}  all=$${dayAll.toFixed(2).padStart(8)}  botero-trade=$${dayWs.toFixed(2).padStart(8)}`)
  }
  console.log(`  TOTAL all=$${totalAll.toFixed(2)}  botero-trade=$${totalWs.toFixed(2)}`)
}

await fetchCost(sevenAgo, tomorrow, '7 days')
await fetchCost(monthStart, tomorrow, 'MTD')
