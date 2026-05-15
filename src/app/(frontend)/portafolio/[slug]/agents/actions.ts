'use server'

import configPromise from '@payload-config'
import { getPayload } from 'payload'
import type { RequiredDataFromCollectionSlug } from 'payload'
import { revalidatePath } from 'next/cache'

import { requireUser } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import type {
  ExecutionType,
  StrategyType,
  ClaudeModel,
} from '@/collections/Bots/domain/rules/botRules'

export type CreateBotInput = {
  portfolioSlug: string
  name: string
  executionType: ExecutionType
  strategyType: StrategyType
  description?: string
  // Agent-only
  model?: ClaudeModel
  systemPrompt?: string
}

export type CreateBotResult =
  | { ok: true; id: string | number; botSlug?: string | null }
  | { ok: false; error: string }

const trim = (value: string | undefined): string | undefined => {
  if (!value) return undefined
  const t = value.trim()
  return t.length === 0 ? undefined : t
}

const VALID_STRATEGIES: StrategyType[] = [
  'quality_value',
  'quality_growth',
  'quality_dividend',
  'speculative_momentum',
  'speculative_gamma',
  'speculative_breakout',
  'speculative_spring',
  'qgarp',
  'momentum',
  'mean_reversion',
  'trend_following',
  'custom',
]

const VALID_MODELS: ClaudeModel[] = ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4']

export async function createBot(input: CreateBotInput): Promise<CreateBotResult> {
  let user: Awaited<ReturnType<typeof requireUser>>
  try {
    user = await requireUser()
  } catch {
    return { ok: false, error: 'Not authenticated.' }
  }

  const name = trim(input.name)
  if (!name) return { ok: false, error: 'Name is required.' }
  if (name.length > 80) return { ok: false, error: 'Name must be 80 characters or fewer.' }

  if (input.executionType !== 'agent' && input.executionType !== 'strategy') {
    return { ok: false, error: 'Invalid execution type.' }
  }
  if (!VALID_STRATEGIES.includes(input.strategyType)) {
    return { ok: false, error: 'Invalid strategy type.' }
  }

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === input.portfolioSlug)
  if (!portfolio) return { ok: false, error: 'Portfolio not found.' }
  if (portfolio.role !== 'owner' && portfolio.role !== 'admin') {
    return { ok: false, error: 'You need admin access on this portfolio to create an agent.' }
  }

  const data: Record<string, unknown> = {
    portfolio: portfolio.id,
    name,
    executionType: input.executionType,
    strategyType: input.strategyType,
    status: 'stopped',
  }

  const description = trim(input.description)
  if (description) data.description = description

  if (input.executionType === 'agent') {
    const model = input.model && VALID_MODELS.includes(input.model) ? input.model : 'claude-sonnet-4-6'
    data.model = model
    const systemPrompt = trim(input.systemPrompt)
    if (systemPrompt) data.systemPrompt = systemPrompt
  }

  const payload = await getPayload({ config: configPromise })

  try {
    const created = await payload.create({
      collection: 'bots',
      data: data as RequiredDataFromCollectionSlug<'bots'>,
      user,
      overrideAccess: false,
    })
    revalidatePath(`/portafolio/${input.portfolioSlug}/agents`)
    return {
      ok: true,
      id: created.id,
      botSlug: (created as { botSlug?: string | null }).botSlug ?? null,
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create agent.'
    return { ok: false, error: message }
  }
}
