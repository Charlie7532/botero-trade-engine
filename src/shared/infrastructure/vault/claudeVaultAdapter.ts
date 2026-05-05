import { IVaultAdapter } from '@/shared/domain/ports/vaultPort'

/**
 * Minimal Claude‑Vault adapter.
 * Uses Claude's HTTP Vault API (documented at https://docs.anthropic.com/claude/vault).
 * All calls are authenticated via the `ANTHROPIC_API_KEY` environment variable – this is the only
 * place we read a secret, and it is never persisted to the database.
 */
export class ClaudeVaultAdapter implements IVaultAdapter {
  private apiKey: string
  private baseUrl: string = 'https://api.anthropic.com/v1/vaults'

  constructor() {
    this.apiKey = process.env.ANTHROPIC_API_KEY ?? ''
    if (!this.apiKey) {
      throw new Error('ANTHROPIC_API_KEY not set – required for ClaudeVaultAdapter')
    }
  }

  async createVault(name: string): Promise<string> {
    const resp = await fetch(this.baseUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name }),
    })
    if (!resp.ok) {
      const txt = await resp.text()
      throw new Error(`Failed to create Claude vault: ${resp.status} ${txt}`)
    }
    const data = await resp.json()
    return data.id // expected field from Claude
  }

  async storeSecret(vaultId: string, key: string, value: string): Promise<void> {
    const url = `${this.baseUrl}/${vaultId}/secrets`
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ key, value }),
    })
    if (!resp.ok) {
      const txt = await resp.text()
      throw new Error(`Failed to store secret in Claude vault: ${resp.status} ${txt}`)
    }
  }

  async fetchSecret(vaultId: string, key: string): Promise<string> {
    const url = `${this.baseUrl}/${vaultId}/secrets/${encodeURIComponent(key)}`
    const resp = await fetch(url, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
      },
    })
    if (!resp.ok) {
      const txt = await resp.text()
      throw new Error(`Failed to fetch secret from Claude vault: ${resp.status} ${txt}`)
    }
    const data = await resp.json()
    return data.value
  }

  async deleteVault(vaultId: string): Promise<void> {
    const url = `${this.baseUrl}/${vaultId}`
    const resp = await fetch(url, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
      },
    })
    if (!resp.ok) {
      const txt = await resp.text()
      throw new Error(`Failed to delete Claude vault: ${resp.status} ${txt}`)
    }
  }
}
