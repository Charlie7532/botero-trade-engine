import {
  IVaultAdapter,
  CreateVaultParams,
  AddCredentialParams,
} from '@/shared/domain/ports/vaultPort'

const API_BASE = 'https://api.anthropic.com/v1'

/**
 * Adapter for Anthropic Managed Agents Vault API.
 * Docs: https://platform.claude.com/docs/en/managed-agents/vaults
 *
 * Authentication: x-api-key header (NOT Authorization: Bearer)
 * Required headers on ALL requests:
 *   - anthropic-version: 2023-06-01
 *   - anthropic-beta: managed-agents-2026-04-01
 */
export class ClaudeVaultAdapter implements IVaultAdapter {
  private apiKey: string

  constructor() {
    this.apiKey = process.env.ANTHROPIC_API_KEY ?? ''
    if (!this.apiKey) {
      throw new Error('ANTHROPIC_API_KEY env var not set')
    }
  }

  private headers() {
    return {
      'x-api-key': this.apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-beta': 'managed-agents-2026-04-01',
      'content-type': 'application/json',
    }
  }

  async createVault(params: CreateVaultParams): Promise<string> {
    const resp = await fetch(`${API_BASE}/vaults`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify({
        display_name: params.displayName,
        metadata: {
          external_portfolio_id: params.externalPortfolioId,
        },
      }),
    })

    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(
        `Vault create failed: ${resp.status} ${resp.statusText} — ${text}`
      )
    }

    const data = await resp.json()
    return data.id
  }

  async addCredential(params: AddCredentialParams): Promise<string> {
    // Shape verificado contra la API real (smoke test):
    // el envelope `auth` es REQUIRED y el campo del secreto se llama `token`.
    const body: Record<string, unknown> = {
      auth: {
        type: 'static_bearer',
        mcp_server_url: params.mcpServerUrl,
        token: params.token,
      },
    }

    if (params.displayName) {
      body.display_name = params.displayName
    }

    const resp = await fetch(
      `${API_BASE}/vaults/${params.vaultId}/credentials`,
      {
        method: 'POST',
        headers: this.headers(),
        body: JSON.stringify(body),
      }
    )

    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(
        `Credential add failed: ${resp.status} ${resp.statusText} — ${text}`
      )
    }

    const data = await resp.json()
    return data.id
  }

  async archiveVault(vaultId: string): Promise<void> {
    const resp = await fetch(
      `${API_BASE}/vaults/${vaultId}/archive`,
      {
        method: 'POST',
        headers: this.headers(),
      }
    )

    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(
        `Vault archive failed: ${resp.status} ${resp.statusText} — ${text}`
      )
    }
  }
}