#!/usr/bin/env node
/**
 * Diagnose the ANTHROPIC_ADMIN_KEY used by the Claude usage widget.
 *
 * Run:  node scripts/check-anthropic-admin-key.mjs
 *
 * Loads .env.local then .env (same precedence as Next.js) and:
 *   1. Confirms the key is present and well-formed.
 *   2. Calls the Admin API to list workspaces (so you can see which
 *      Anthropic "project" / org this key belongs to).
 *   3. Pulls the last 7 days of cost + usage and prints totals.
 *
 * Never prints the key itself, only a masked fingerprint.
 */

import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const envFiles = ['.env.local', '.env'] // Next.js precedence: .env.local wins

function loadEnvFile(file) {
  const full = path.join(root, file)
  if (!fs.existsSync(full)) return { loaded: false, vars: {} }
  const text = fs.readFileSync(full, 'utf8')
  const vars = {}
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq === -1) continue
    const key = line.slice(0, eq).trim()
    let val = line.slice(eq + 1).trim()
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1)
    }
    if (!(key in vars)) vars[key] = val
  }
  return { loaded: true, vars }
}

const sources = {}
for (const file of envFiles) {
  const { loaded, vars } = loadEnvFile(file)
  sources[file] = { loaded, vars }
}

// Merge with .env.local precedence
const merged = { ...sources['.env'].vars, ...sources['.env.local'].vars }
const KEY = merged.ANTHROPIC_ADMIN_KEY || process.env.ANTHROPIC_ADMIN_KEY

console.log('── Env file scan ──────────────────────────────────────────')
for (const f of envFiles) {
  const s = sources[f]
  if (!s.loaded) {
    console.log(`  ${f}: (missing)`)
    continue
  }
  const has = 'ANTHROPIC_ADMIN_KEY' in s.vars
  console.log(`  ${f}: loaded   ANTHROPIC_ADMIN_KEY=${has ? 'present' : 'MISSING'}`)
}

if (!KEY) {
  console.log('\n✗ No ANTHROPIC_ADMIN_KEY found. Add it to .env.local')
  process.exit(1)
}

const fingerprint = `${KEY.slice(0, 12)}…${KEY.slice(-4)}  (len ${KEY.length})`
const looksAdmin = KEY.startsWith('sk-ant-admin')
console.log(`\n  Key fingerprint: ${fingerprint}`)
console.log(`  Looks like Admin Key (sk-ant-admin…): ${looksAdmin ? 'YES' : 'NO ✗'}`)
if (!looksAdmin) {
  console.log('  ⚠ Admin endpoints require an Admin Key. Generate one at:')
  console.log('    console.anthropic.com → Settings → Admin Keys')
  process.exit(1)
}

const headers = {
  'anthropic-version': '2023-06-01',
  'x-api-key': KEY,
  'content-type': 'application/json',
}

async function call(label, url) {
  process.stdout.write(`\n→ ${label}\n  ${url}\n`)
  try {
    const res = await fetch(url, { headers })
    const text = await res.text()
    let body
    try { body = JSON.parse(text) } catch { body = text }
    console.log(`  status: ${res.status} ${res.statusText}`)
    if (!res.ok) {
      console.log(`  body  : ${typeof body === 'string' ? body.slice(0, 400) : JSON.stringify(body).slice(0, 400)}`)
      return null
    }
    return body
  } catch (err) {
    console.log(`  fetch error: ${err.message}`)
    return null
  }
}

const now = new Date()
const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
const range = new URLSearchParams({
  starting_at: sevenDaysAgo.toISOString(),
  ending_at: now.toISOString(),
  bucket_width: '1d',
})

// 1. Workspaces (Anthropic's "projects")
const ws = await call(
  'Workspaces visible to this key',
  'https://api.anthropic.com/v1/organizations/workspaces',
)
if (ws?.data?.length) {
  console.log('  workspaces:')
  for (const w of ws.data) {
    console.log(`    • ${w.name}   id=${w.id}   archived=${w.archived_at ? 'yes' : 'no'}`)
  }
} else if (ws) {
  console.log('  (no workspaces returned — org has none, or key lacks permission)')
}

// 2. Cost report (last 7 days)
const cost = await call(
  'Cost report (last 7 days, daily)',
  `https://api.anthropic.com/v1/organizations/cost_report?${range}`,
)
if (cost?.data) {
  const bucketTotal = (b) => (b.results ?? []).reduce((s, r) => s + Number(r.amount ?? 0), 0)
  const totalUsd = cost.data.reduce((s, b) => s + bucketTotal(b), 0)
  const nonZero = cost.data.filter((b) => bucketTotal(b) > 0)
  console.log(`  buckets: ${cost.data.length}    non-zero days: ${nonZero.length}`)
  console.log(`  7-day total: $${totalUsd.toFixed(4)}`)
  for (const b of cost.data) {
    console.log(`    ${b.starting_at}  $${bucketTotal(b).toFixed(4)}  (rows=${(b.results ?? []).length})`)
  }
}

// 3. Usage report (last 7 days)
const usage = await call(
  'Usage report messages (last 7 days, daily)',
  `https://api.anthropic.com/v1/organizations/usage_report/messages?${range}`,
)
if (usage?.data) {
  const t = usage.data.reduce(
    (a, b) => {
      for (const r of b.results ?? []) {
        a.input += Number(r.uncached_input_tokens ?? 0)
        a.output += Number(r.output_tokens ?? 0)
        a.cacheWrite +=
          Number(r.cache_creation_input_tokens ?? 0) +
          Number(r.cache_creation?.ephemeral_1h_input_tokens ?? 0) +
          Number(r.cache_creation?.ephemeral_5m_input_tokens ?? 0)
        a.cacheRead += Number(r.cache_read_input_tokens ?? 0)
      }
      return a
    },
    { input: 0, output: 0, cacheWrite: 0, cacheRead: 0 },
  )
  const fmt = (n) => new Intl.NumberFormat('en-US').format(n)
  console.log(`  buckets: ${usage.data.length}`)
  console.log(`  input ${fmt(t.input)}  output ${fmt(t.output)}  cache_write ${fmt(t.cacheWrite)}  cache_read ${fmt(t.cacheRead)}`)
}

console.log('\n── Done ──────────────────────────────────────────────────')
console.log('Notes:')
console.log(' • Admin keys are ORG-scoped, not project-scoped. The widget shows the')
console.log('   aggregate of every workspace in the org the key belongs to.')
console.log(' • To restrict to a specific workspace (e.g. "botero-trade"), pass')
console.log('   &workspace_ids[]=<id> to the cost_report / usage_report URLs.')
console.log(' • Usage data can lag up to ~1 hour. If you just started using Claude')
console.log('   Code, totals may show $0 until the next aggregation window.')
