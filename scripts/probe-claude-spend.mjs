import fs from 'node:fs'
const txt = fs.readFileSync('.env.local','utf8')+'\n'+fs.readFileSync('.env','utf8')
const m = txt.match(/^\s*ANTHROPIC_ADMIN_KEY\s*=\s*([^\r\n]+)/m)
const KEY = m[1].replace(/^["']|["']$/g,'')
const H = { 'anthropic-version':'2023-06-01', 'x-api-key':KEY }
const WS = 'wrkspc_01HkPJ9qYoxPjbAifCBLfrAG'
const now = new Date()
const todayUtc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
const tomorrowUtc = new Date(todayUtc.getTime() + 864e5)
const sevenAgo = new Date(todayUtc.getTime() - 6*864e5)
const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
function mkQ(from, to, ws) {
  const p = new URLSearchParams({ starting_at: from.toISOString(), ending_at: to.toISOString(), bucket_width:'1d' })
  if (ws) p.append('workspace_ids[]', ws)
  return p
}
const sumB = b => (b.results ?? []).reduce((s,r) => s + Number(r.amount ?? 0), 0)
for (const [label, from, to, ws] of [
  ['7d  botero-trade', sevenAgo, tomorrowUtc, WS],
  ['MTD botero-trade', monthStart, tomorrowUtc, WS],
  ['7d  org-wide    ', sevenAgo, tomorrowUtc, null],
  ['MTD org-wide    ', monthStart, tomorrowUtc, null],
]) {
  const r = await fetch('https://api.anthropic.com/v1/organizations/cost_report?' + mkQ(from, to, ws), { headers: H })
  const j = await r.json()
  const tot = (j.data || []).reduce((s,b) => s + sumB(b), 0)
  console.log(`[${label}] total $${tot.toFixed(4)}  buckets=${(j.data||[]).length}`)
  for (const b of (j.data || [])) {
    console.log('   ', b.starting_at, '$' + sumB(b).toFixed(4))
  }
}
