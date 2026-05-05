import { ClaudeVaultAdapter } from '@/shared/infrastructure/vault/claudeVaultAdapter'
import { IVaultAdapter } from '@/shared/domain/ports/vaultPort'

/**
 * Factory that returns a concrete vault adapter based on the
 * `VAULT_PROVIDER` environment variable. Currently supported values:
 * - 'claude'   (default) – uses the ClaudeVaultAdapter
 * - 'generic'  – placeholder for a future generic vault implementation.
 */
export function getVaultAdapter(): IVaultAdapter {
  const provider = process.env.VAULT_PROVIDER ?? 'claude'
  switch (provider) {
    case 'claude':
      return new ClaudeVaultAdapter()
    case 'generic':
      // For now we fall back to the Claude adapter; replace with a real
      // generic implementation when available.
      return new ClaudeVaultAdapter()
    default:
      throw new Error(`Unsupported VAULT_PROVIDER: ${provider}`)
  }
}
