import type { CollectionAfterChangeHook } from 'payload'
import { getVaultAdapter } from '@/shared/infrastructure/vaultFactory'

/**
 * After a BrokerAccount is saved, ensure a vault exists and store the
 * credentials inside it. The vault ID and sync status are persisted on
 * the document for later retrieval by the Managed Agent Session.
 */
export const syncVaultOnSave: CollectionAfterChangeHook = async ({
  doc,
  req,
  context,
}) => {
  // Prevent infinite loops
  if (context?.skipVaultSync) return doc

  // Only sync if the adapter is available (ANTHROPIC_API_KEY must be set)
  if (!process.env.ANTHROPIC_API_KEY) return doc

  try {
    const adapter = getVaultAdapter()
    const vaultName = `broker-${doc.id}`

    // Create vault if we don't have one yet
    let vaultId = doc.vaultId as string | undefined
    if (!vaultId) {
      vaultId = await adapter.createVault(vaultName)
    }

    // Store each credential as a secret inside the vault
    const secrets: Record<string, string> = {}
    if (doc.apiKeyPlaintext) secrets['apiKey'] = doc.apiKeyPlaintext
    if (doc.secretKeyPlaintext) secrets['secretKey'] = doc.secretKeyPlaintext
    if (doc.ibAccountId) secrets['ibAccountId'] = doc.ibAccountId

    for (const [key, value] of Object.entries(secrets)) {
      await adapter.storeSecret(vaultId, key, value)
    }

    // Update the document with vault metadata
    await req.payload.update({
      collection: 'broker-accounts',
      id: doc.id,
      data: {
        vaultId,
        credentialId: vaultId,
        vaultSyncStatus: 'synced',
      },
      overrideAccess: true,
      context: { skipVaultSync: true },
    })

    console.log(`[VaultSync] Synced vault for broker account ${doc.id}`)
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown vault sync error'
    console.error(`[VaultSync] FAILED for broker account ${doc.id}:`, message)

    await req.payload.update({
      collection: 'broker-accounts',
      id: doc.id,
      data: {
        vaultSyncStatus: 'error',
      },
      overrideAccess: true,
      context: { skipVaultSync: true },
    })
  }

  return doc
}
