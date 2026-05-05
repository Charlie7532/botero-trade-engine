const API_BASE = 'https://api.anthropic.com/v1'
const BETA_HEADER = 'managed-agents-2026-04-01'

type McpServerConfig = {
  name: string
  type: 'url'
  url: string
}

type ToolConfig = {
  type: string
  mcp_server_name?: string
  default_config?: {
    permission_policy: { type: string }
  }
}

type AgentConfig = {
  description?: string
  mcp_servers?: McpServerConfig[]
  metadata?: Record<string, string>
  model: string
  name: string
  skills?: Array<{ name: string }>
  system?: string
  tools?: ToolConfig[]
}

type AgentResponse = {
  archived_at: null | string
  created_at: string
  id: string
  model: { id: string; speed: string }
  name: string
  updated_at: string
  version: number
}

function getApiKey(): string {
  const key = process.env.ANTHROPIC_API_KEY
  if (!key) throw new Error('ANTHROPIC_API_KEY not set in environment')
  return key
}

function headers(): Record<string, string> {
  return {
    'anthropic-beta': BETA_HEADER,
    'anthropic-version': '2023-06-01',
    'content-type': 'application/json',
    'x-api-key': getApiKey(),
  }
}

export async function createAgent(config: AgentConfig): Promise<{ id: string; version: number }> {
  const body: Record<string, unknown> = {
    name: config.name,
    model: config.model,
  }

  if (config.system) body.system = config.system
  if (config.description) body.description = config.description
  if (config.mcp_servers?.length) body.mcp_servers = config.mcp_servers
  if (config.metadata) body.metadata = config.metadata

  // Build tools array: always include agent_toolset + one mcp_toolset per MCP server
  const tools: ToolConfig[] = [{ type: 'agent_toolset_20260401' }]
  if (config.mcp_servers?.length) {
    for (const mcp of config.mcp_servers) {
      tools.push({
        type: 'mcp_toolset',
        mcp_server_name: mcp.name,
        default_config: {
          permission_policy: { type: 'always_allow' },
        },
      })
    }
  }
  body.tools = tools

  if (config.skills?.length) body.skills = config.skills

  const res = await fetch(`${API_BASE}/agents`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Anthropic createAgent failed (${res.status}): ${text.slice(0, 200)}`)
  }

  const data = (await res.json()) as AgentResponse
  return { id: data.id, version: data.version }
}

export async function updateAgent(
  agentId: string,
  version: number,
  config: Partial<AgentConfig>,
): Promise<{ id: string; version: number }> {
  const body: Record<string, unknown> = { version }

  if (config.name) body.name = config.name
  if (config.model) body.model = config.model
  if (config.system !== undefined) body.system = config.system
  if (config.description !== undefined) body.description = config.description
  if (config.mcp_servers !== undefined) body.mcp_servers = config.mcp_servers
  if (config.metadata) body.metadata = config.metadata

  // Rebuild tools if MCP servers changed
  if (config.mcp_servers !== undefined) {
    const tools: ToolConfig[] = [{ type: 'agent_toolset_20260401' }]
    if (config.mcp_servers?.length) {
      for (const mcp of config.mcp_servers) {
        tools.push({
          type: 'mcp_toolset',
          mcp_server_name: mcp.name,
          default_config: {
            permission_policy: { type: 'always_allow' },
          },
        })
      }
    }
    body.tools = tools
  }

  if (config.skills !== undefined) body.skills = config.skills

  const res = await fetch(`${API_BASE}/agents/${agentId}`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Anthropic updateAgent failed (${res.status}): ${text.slice(0, 200)}`)
  }

  const data = (await res.json()) as AgentResponse
  return { id: data.id, version: data.version }
}

export async function getAgent(agentId: string): Promise<AgentResponse | null> {
  const res = await fetch(`${API_BASE}/agents/${agentId}`, {
    method: 'GET',
    headers: headers(),
  })

  if (res.status === 404) return null
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Anthropic getAgent failed (${res.status}): ${text.slice(0, 200)}`)
  }

  return (await res.json()) as AgentResponse
}

export async function archiveAgent(agentId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/archive`, {
    method: 'POST',
    headers: headers(),
  })

  if (!res.ok && res.status !== 404) {
    const text = await res.text().catch(() => '')
    throw new Error(`Anthropic archiveAgent failed (${res.status}): ${text.slice(0, 200)}`)
  }
}
