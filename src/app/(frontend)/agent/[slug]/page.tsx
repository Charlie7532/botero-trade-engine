import { notFound } from 'next/navigation'
import { getPayload } from 'payload'
import config from '@payload-config'
import { AgentChat } from '@/components/AgentChat'

export default async function AgentPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const payload = await getPayload({ config })

  const bots = await payload.find({
    collection: 'bots',
    where: { botSlug: { equals: slug } },
    limit: 1,
    depth: 0,
    overrideAccess: true,
  })

  if (bots.totalDocs === 0) notFound()

  const bot = bots.docs[0] as any

  if (bot.executionType !== 'agent') notFound()

  return (
    <AgentChat
      botSlug={slug}
      botName={bot.name}
      botDescription={bot.description || ''}
      modelName={bot.model || 'claude-sonnet-4-6'}
    />
  )
}
