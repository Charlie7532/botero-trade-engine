import fs from 'node:fs'
const env = Object.fromEntries(fs.readFileSync('.env.local','utf8').split('\n').map(l=>l.match(/^([A-Z0-9_]+)=(.*)$/)).filter(Boolean).map(m=>[m[1], m[2].replace(/^['"]|['"]$/g,'').trim()]))
const { NEON_API_KEY: KEY, NEON_PROJECT_ID: PROJ } = env
const BASE = 'https://console.neon.tech/api/v2'
const headers = { Authorization: `Bearer ${KEY}`, Accept: 'application/json' }

const now = Math.floor(Date.now()/1000), day = now - 86400
const fromIso = new Date(day*1000).toISOString()
const toIso = new Date(now*1000).toISOString()

async function go(label, path, params) {
  const u = new URL(BASE + path)
  if (params) for (const [k,v] of Object.entries(params)) u.searchParams.set(k, String(v))
  const r = await fetch(u, { headers })
  const t = await r.text()
  let b; try { b = JSON.parse(t) } catch { b = t.slice(0,300) }
  console.log(`\n[${r.status}] ${label}  ${u.pathname}${u.search.length<120?u.search:''}`)
  if (typeof b === 'object' && b) {
    console.log('keys:', Object.keys(b).join(','))
    for (const k of Object.keys(b).slice(0,4)) {
      const v = b[k]
      if (Array.isArray(v) && v[0]) console.log(`  ${k}[0]:`, JSON.stringify(v[0]).slice(0,260))
      else if (v && typeof v === 'object') console.log(`  ${k}:`, JSON.stringify(v).slice(0,260))
      else console.log(`  ${k}:`, JSON.stringify(v))
    }
  } else console.log('body:', b)
}

await go('me',                  '/users/me')
await go('orgs',                '/users/me/organizations')
await go('consumption acct',    '/consumption_history/account', { from: fromIso, to: toIso, granularity: 'hourly' })
await go('consumption proj',    '/consumption_history/projects', { from: fromIso, to: toIso, granularity: 'hourly', project_ids: PROJ })
await go('proj consumption',    `/projects/${PROJ}/consumption_history`, { from: fromIso, to: toIso, granularity: 'hourly' })
