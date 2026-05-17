/**
 * Anthropic Admin API client + types for the Claude usage widget.
 * Server-only. Never import from a "use client" file.
 *
 * Endpoints used (all under https://api.anthropic.com):
 *   GET /v1/organizations/me
 *   GET /v1/organizations/usage_report/messages
 *   GET /v1/organizations/cost_report
 *
 * Real response shapes were verified empirically — top-level buckets carry
 * `starting_at` (ISO) and a `results[]` array. Cost rows expose `amount` as a
 * USD string; usage rows expose token counters plus a nested `cache_creation`.
 */

export type UsageResult = {
  uncached_input_tokens?: number
  output_tokens?: number
  cache_read_input_tokens?: number
  cache_creation_input_tokens?: number
  cache_creation?: {
    ephemeral_1h_input_tokens?: number
    ephemeral_5m_input_tokens?: number
  }
}

export type UsageBucket = {
  starting_at: string
  results?: UsageResult[]
}

export type CostResult = {
  amount?: string | number
  currency?: string
  workspace_id?: string | null
  description?: string | null
  model?: string | null
  token_type?: string | null
}

export type CostBucket = {
  starting_at: string
  results?: CostResult[]
}

const BASE = 'https://api.anthropic.com/v1/organizations'
const REVALIDATE_SECONDS = 60

function num(v: unknown): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const p = Number(v)
    return Number.isFinite(p) ? p : 0
  }
  return 0
}

export function bucketCostUsd(b: CostBucket, workspaceIds?: ReadonlySet<string>): number {
  return (b.results ?? [])
    .filter((r) => {
      if (!workspaceIds || workspaceIds.size === 0) return true
      return r.workspace_id ? workspaceIds.has(r.workspace_id) : false
    })
    .reduce((s, r) => s + num(r.amount), 0)
}

export function bucketTokens(b: UsageBucket): {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
} {
  return (b.results ?? []).reduce(
    (a, r) => {
      const cacheCreate =
        num(r.cache_creation_input_tokens) +
        num(r.cache_creation?.ephemeral_1h_input_tokens) +
        num(r.cache_creation?.ephemeral_5m_input_tokens)
      return {
        input: a.input + num(r.uncached_input_tokens),
        output: a.output + num(r.output_tokens),
        cacheRead: a.cacheRead + num(r.cache_read_input_tokens),
        cacheWrite: a.cacheWrite + cacheCreate,
      }
    },
    { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  )
}

export function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return new Intl.NumberFormat('en-US').format(value)
}

async function call<T>(path: string, search?: URLSearchParams): Promise<T | null> {
  const adminKey = process.env.ANTHROPIC_ADMIN_KEY
  if (!adminKey) return null
  const url = search ? `${BASE}${path}?${search}` : `${BASE}${path}`
  try {
    const res = await fetch(url, {
      headers: { 'anthropic-version': '2023-06-01', 'x-api-key': adminKey },
      next: { revalidate: REVALIDATE_SECONDS },
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

/**
 * Anthropic caps `limit=31` for 1d buckets. Follow `next_page` cursor to
 * stitch together a wider window. `pageCap` is a safety stop.
 */
async function callPaged<R>(
  path: string,
  baseParams: URLSearchParams,
  pageCap = 8,
): Promise<{ data: R[] } | null> {
  type Page = { data?: R[]; has_more?: boolean; next_page?: string | null }
  const collected: R[] = []
  let cursor: string | null = null
  for (let i = 0; i < pageCap; i++) {
    const params = new URLSearchParams(baseParams)
    if (cursor) params.set('page', cursor)
    const page = await call<Page>(path, params)
    if (!page) return collected.length > 0 ? { data: collected } : null
    if (page.data) collected.push(...page.data)
    if (!page.has_more || !page.next_page) break
    cursor = page.next_page
  }
  return { data: collected }
}

export type ClaudeUsageSnapshot = {
  orgName: string | null
  workspaceName: string | null
  workspaceIds: string[]
  scope: 'workspace' | 'organization'
  /** UTC midnight of the first day in `costBuckets` (window start). */
  windowStart: string
  /** UTC midnight after the last possible bucket (exclusive end). */
  windowEnd: string
  /** Daily cost buckets, `group_by[]=workspace_id` — rows carry workspace_id. */
  costBuckets: CostBucket[]
  /** Daily cost buckets, `group_by[]=description` — rows are org-wide (workspace_id=null). */
  descriptionBuckets: CostBucket[]
  /** Daily usage buckets filtered by `workspace_ids[]` when scope='workspace'. */
  usageBuckets: UsageBucket[]
  error: 'missing-key' | 'fetch-failed' | null
}

/**
 * cost_report's `workspace_ids[]` filter is silently broken (returns 0 buckets).
 * Use `group_by[]=workspace_id` and filter client-side.
 * usage_report/messages DOES accept `workspace_ids[]` correctly.
 */
function buildCostRange(
  from: Date,
  to: Date,
  groupBy: 'workspace_id' | 'description',
): URLSearchParams {
  const params = new URLSearchParams({
    starting_at: from.toISOString(),
    ending_at: to.toISOString(),
    bucket_width: '1d',
    limit: '31',
  })
  params.append('group_by[]', groupBy)
  return params
}

function buildUsageRange(from: Date, to: Date, workspaceIds: string[]): URLSearchParams {
  const params = new URLSearchParams({
    starting_at: from.toISOString(),
    ending_at: to.toISOString(),
    bucket_width: '1d',
    limit: '31',
  })
  for (const id of workspaceIds) params.append('workspace_ids[]', id)
  return params
}

export async function loadClaudeUsage(): Promise<ClaudeUsageSnapshot> {
  // ANTHROPIC_WORKSPACE_ID may be a single ID or a comma-separated list.
  const workspaceIds = (process.env.ANTHROPIC_WORKSPACE_ID ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const scope: 'workspace' | 'organization' = workspaceIds.length > 0 ? 'workspace' : 'organization'

  // Anthropic buckets are aligned to UTC midnight. Use UTC boundaries and
  // extend `ending_at` past tomorrow's UTC midnight so today's partial bucket
  // is always included. Fetch a wide 90-day window so the client can pick any
  // range (Today / 7d / 30d / MTD / Last month) without a re-fetch.
  const now = new Date()
  const todayUtcStart = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  )
  const tomorrowUtcStart = new Date(todayUtcStart.getTime() + 24 * 60 * 60 * 1000)
  const windowStart = new Date(todayUtcStart.getTime() - 89 * 24 * 60 * 60 * 1000)

  if (!process.env.ANTHROPIC_ADMIN_KEY) {
    return {
      orgName: null,
      workspaceName: null,
      workspaceIds,
      scope,
      windowStart: windowStart.toISOString(),
      windowEnd: tomorrowUtcStart.toISOString(),
      costBuckets: [],
      descriptionBuckets: [],
      usageBuckets: [],
      error: 'missing-key',
    }
  }

  const costParams = buildCostRange(windowStart, tomorrowUtcStart, 'workspace_id')
  const descParams = buildCostRange(windowStart, tomorrowUtcStart, 'description')
  const usageParams = buildUsageRange(windowStart, tomorrowUtcStart, workspaceIds)

  const [org, workspaces, costRes, descRes, usageRes] = await Promise.all([
    call<{ name?: string }>('/me'),
    workspaceIds.length > 0
      ? call<{ data: Array<{ id: string; name: string }> }>('/workspaces')
      : Promise.resolve(null),
    callPaged<CostBucket>('/cost_report', costParams),
    callPaged<CostBucket>('/cost_report', descParams),
    callPaged<UsageBucket>('/usage_report/messages', usageParams),
  ])

  const matchedNames =
    workspaceIds.length > 0
      ? workspaceIds
          .map((id) => workspaces?.data?.find((w) => w.id === id)?.name)
          .filter((n): n is string => Boolean(n))
      : []
  const workspaceName =
    matchedNames.length > 0
      ? matchedNames.length <= 2
        ? matchedNames.join(' + ')
        : `${matchedNames.length} workspaces`
      : null

  const fetchFailed = costRes == null && usageRes == null
  return {
    orgName: org?.name ?? null,
    workspaceName,
    workspaceIds,
    scope,
    windowStart: windowStart.toISOString(),
    windowEnd: tomorrowUtcStart.toISOString(),
    costBuckets: costRes?.data ?? [],
    descriptionBuckets: descRes?.data ?? [],
    usageBuckets: usageRes?.data ?? [],
    error: fetchFailed ? 'fetch-failed' : null,
  }
}
