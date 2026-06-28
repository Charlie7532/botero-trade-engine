/**
 * Port (contract) for vault adapters.
 *
 * Aligned with Anthropic Managed Agents API:
 * - Credentials are write-only (no fetchSecret)
 * - Use archive instead of hard delete for audit trail
 * - Vaults are tagged with external_portfolio_id metadata for reconciliation
 *   on Botero's side. The API does NOT support filtering vaults by metadata,
 *   so portfolio -> vault resolution lives in Botero's own DB, not here.
 */

export interface CreateVaultParams {
  /** Display name for the vault (max 255 chars) */
  displayName: string
  /** Internal portfolio ID to tag the vault with (audit / reconciliation) */
  externalPortfolioId: string
}

export interface AddCredentialParams {
  /** ID of the vault to add the credential to */
  vaultId: string
  /** Full HTTPS URL of the MCP server this credential authenticates against */
  mcpServerUrl: string
  /** Bearer token to inject into requests to the MCP server */
  token: string
  /** Optional display name for the credential (max 255 chars) */
  displayName?: string
}

export interface IVaultAdapter {
  /** Create a new vault tagged with external_portfolio_id metadata */
  createVault(params: CreateVaultParams): Promise<string>

  /** Add a static_bearer credential to a vault (write-only on Anthropic) */
  addCredential(params: AddCredentialParams): Promise<string>

  /** Archive a vault (preserves audit trail; use instead of hard delete) */
  archiveVault(vaultId: string): Promise<void>
}