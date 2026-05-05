/**
 * Seed Agent Skills from .agents/skills/ directory.
 *
 * Usage: npx tsx src/scripts/seedAgentSkills.ts
 *
 * Reads each SKILL.md, extracts YAML frontmatter (name, description),
 * and creates AgentSkills collection records if they don't already exist.
 */
import 'dotenv/config'
import fs from 'fs'
import path from 'path'
import { getPayload } from 'payload'
import config from '@payload-config'

// Only trading & market-related skills — dev/architecture skills are excluded
const TRADING_SKILLS: Record<string, string> = {
  'backtesting-trading-strategies': 'research',
  'fundamental-analyst': 'analysis',
  'operational-purpose': 'general',
  'risk-manager': 'risk',
  'tactical-entries': 'execution',
  'trading-analysis': 'analysis',
}

function parseFrontmatter(content: string): { name: string; description: string; body: string } {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/)
  if (!match) return { name: '', description: '', body: content }

  const frontmatter = match[1]!
  const body = match[2]!.trim()

  let name = ''
  let description = ''

  // Extract name
  const nameMatch = frontmatter.match(/^name:\s*(.+)$/m)
  if (nameMatch) name = nameMatch[1]!.trim()

  // Extract description (may be multi-line with |)
  const descMatch = frontmatter.match(/description:\s*\|?\s*\r?\n([\s\S]*?)(?=\r?\n\w|\r?\n---|\r?\n$|$)/)
  if (descMatch) {
    description = descMatch[1]!
      .split(/\r?\n/)
      .map((l) => l.replace(/^\s{2}/, ''))
      .join(' ')
      .trim()
  } else {
    const singleDescMatch = frontmatter.match(/^description:\s*(.+)$/m)
    if (singleDescMatch) description = singleDescMatch[1]!.trim()
  }

  return { name, description, body }
}

async function main() {
  const payload = await getPayload({ config })

  const skillsDir = path.resolve(process.cwd(), '.agents', 'skills')
  if (!fs.existsSync(skillsDir)) {
    console.error('.agents/skills/ directory not found')
    process.exit(1)
  }

  const folders = fs.readdirSync(skillsDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())

  let created = 0
  let skipped = 0

  for (const folder of folders) {
    // Only seed trading/market skills
    if (!TRADING_SKILLS[folder.name]) {
      continue
    }

    const skillMd = path.join(skillsDir, folder.name, 'SKILL.md')
    if (!fs.existsSync(skillMd)) {
      console.log(`  SKIP ${folder.name} (no SKILL.md)`)
      skipped++
      continue
    }

    const raw = fs.readFileSync(skillMd, 'utf-8')
    const { name, description, body } = parseFrontmatter(raw)

    if (!name) {
      console.log(`  SKIP ${folder.name} (no name in frontmatter)`)
      skipped++
      continue
    }

    // Check if already exists
    const existing = await payload.find({
      collection: 'agent-skills',
      where: { slug: { equals: folder.name } },
      limit: 1,
      overrideAccess: true,
    })

    if (existing.totalDocs > 0) {
      console.log(`  EXISTS ${name} (${folder.name})`)
      skipped++
      continue
    }

    // Prettify name: "fundamental-analyst" → "Fundamental Analyst"
    const displayName = name
      .split('-')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ')

    await payload.create({
      collection: 'agent-skills',
      data: {
        name: displayName,
        slug: folder.name,
        description,
        type: 'custom',
        category: (TRADING_SKILLS[folder.name] || 'general') as any,
        isActive: true,
        promptContent: body,
      },
      overrideAccess: true,
    })

    console.log(`  CREATED ${displayName} (${folder.name})`)
    created++
  }

  console.log(`\nDone. Created: ${created}, Skipped: ${skipped}`)
  process.exit(0)
}

main().catch((err) => {
  console.error('Seed failed:', err)
  process.exit(1)
})
