export interface IVaultAdapter {
  /**
   * Create a new vault and return its external identifier.
   */
  createVault(name: string): Promise<string>

  /**
   * Store a secret value under a given key inside the specified vault.
   */
  storeSecret(vaultId: string, key: string, value: string): Promise<void>

  /**
   * Retrieve a secret value by key from a vault.
   */
  fetchSecret(vaultId: string, key: string): Promise<string>

  /**
   * Delete a vault and all its contents.
   */
  deleteVault(vaultId: string): Promise<void>
}
