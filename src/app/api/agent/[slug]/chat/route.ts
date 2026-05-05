import { NextRequest, NextResponse } from 'next/server'
import { getPayload } from 'payload'
import config from '@payload-config'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params

  try {
    const payload = await getPayload({ config })

    // Look up bot by slug
    const bots = await payload.find({
      collection: 'bots',
      where: { botSlug: { equals: slug } },
      limit: 1,
      depth: 2, // resolve skills
      overrideAccess: true,
    })

    if (bots.totalDocs === 0) {
      return NextResponse.json({ error: 'Agent not found' }, { status: 404 })
    }

    const bot = bots.docs[0] as any

    if (bot.executionType !== 'agent') {
      return NextResponse.json({ error: 'Not an AI agent' }, { status: 400 })
    }

    const apiKey = process.env.ANTHROPIC_API_KEY
    if (!apiKey) {
      return NextResponse.json({ error: 'API key not configured' }, { status: 500 })
    }

    const body = await request.json()
    const { messages, sessionId } = body

    if (!messages || !Array.isArray(messages)) {
      return NextResponse.json({ error: 'messages array required' }, { status: 400 })
    }

    // Build system prompt with custom skills
    let systemPrompt = bot.systemPrompt || ''
    if (bot.skills && Array.isArray(bot.skills)) {
      const customPrompts: string[] = []
      for (const skill of bot.skills) {
        if (typeof skill === 'object' && skill?.type === 'custom' && skill?.promptContent) {
          customPrompts.push(`## Skill: ${skill.name}\n${skill.promptContent}`)
        }
      }
      if (customPrompts.length > 0) {
        systemPrompt += '\n\n---\n\n# Active Skills\n\n' + customPrompts.join('\n\n')
      }
    }

    // Resolve vault IDs for Managed Agent Session
    const vaultIds: string[] = []

    // 1. Broker vault from active BotAssignment
    const assignments = await payload.find({
      collection: 'bot-assignments',
      where: {
        bot: { equals: bot.id },
        isActive: { equals: true },
      },
      limit: 1,
      depth: 1,
      overrideAccess: true,
    })

    if (assignments.totalDocs > 0) {
      const assignment = assignments.docs[0] as any
      const brokerAccount =
        typeof assignment.brokerAccount === 'object'
          ? assignment.brokerAccount
          : null

      if (brokerAccount?.vaultId) {
        vaultIds.push(brokerAccount.vaultId)
      }
    }

    // 2. Platform vault (global project vault, if configured)
    const platformVaults = await payload.find({
      collection: 'project-vaults',
      where: { status: { equals: 'ready' } },
      limit: 10,
      overrideAccess: true,
    })
    for (const pv of platformVaults.docs) {
      const pvDoc = pv as any
      if (pvDoc.vaultId) {
        vaultIds.push(pvDoc.vaultId)
      }
    }

    // Use Managed Agent Session if bot has an agentId and we have vault IDs
    if (bot.agentId && vaultIds.length > 0) {
      // Create or resume a Managed Agent Session
      const sessionPayload: Record<string, any> = {
        agent_id: bot.agentId,
        messages,
        vault_ids: vaultIds,
      }

      if (sessionId) {
        sessionPayload.session_id = sessionId
      }

      const sessionRes = await fetch('https://api.anthropic.com/v1/agent/sessions', {
        method: 'POST',
        headers: {
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
          'anthropic-beta': 'managed-agents-2026-04-01',
          'content-type': 'application/json',
        },
        body: JSON.stringify(sessionPayload),
      })

      if (!sessionRes.ok) {
        const errorText = await sessionRes.text().catch(() => '')
        console.error('[AgentChat] Session error:', sessionRes.status, errorText.slice(0, 300))
        return NextResponse.json(
          { error: `Agent session error (${sessionRes.status})` },
          { status: 502 },
        )
      }

      const data = await sessionRes.json()
      return NextResponse.json(data)
    }

    // Fallback: standard Messages API (no vaults needed)
    const anthropicRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: bot.model || 'claude-sonnet-4-6',
        max_tokens: 4096,
        system: systemPrompt || undefined,
        messages,
      }),
    })

    if (!anthropicRes.ok) {
      const errorText = await anthropicRes.text().catch(() => '')
      console.error('[AgentChat] Anthropic error:', anthropicRes.status, errorText.slice(0, 300))
      return NextResponse.json(
        { error: `Anthropic API error (${anthropicRes.status})` },
        { status: 502 },
      )
    }

    const data = await anthropicRes.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error('[AgentChat] Error:', err)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
