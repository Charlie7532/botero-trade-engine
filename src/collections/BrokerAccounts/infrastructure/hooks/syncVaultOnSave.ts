import type { CollectionAfterChangeHook } from 'payload'
import { getVaultAdapter } from '@/shared/infrastructure/vaultFactory'

/**
 * After a BrokerAccount is saved, ensure an Anthropic vault exists for the
 * portfolio and that it holds the MCP auth credential.
 *
 * Credential model (Opción A): the credential is a shared secret that
 * authenticates Claude -> the broker's MCP server. The broker's real API keys
 * are NOT stored here; they live as env vars on the MCP server. So this hook
 * reads the shared secret + MCP URL from env, never from the broker plaintexts
 * (which beforeChange already encrypted and removed). That is why there is no
 * req.context plaintext stash here.
 */

// Per-broker MCP config sourced from env vars. `token` is the shared secret that
// must match what the MCP server validates; `url` is where that server lives.
// Names are a proposal — JC confirms/sets the actual values.
function getMcpConfig(brokerType: string): { url?: string; token?: string } | null {
  switch (brokerType) {
    case 'alpaca':
      return { url: process.env.ALPACA_MCP_URL, token: process.env.ALPACA_MCP_TOKEN }
    case 'interactive_brokers':
      return { url: process.env.IB_MCP_URL, token: process.env.IB_MCP_TOKEN }
    default:
      return null
  }
}

export const syncVaultOnSave: CollectionAfterChangeHook = async ({
  doc,
  req,
  context,
}) => {
  // Prevent infinite loops (the status updates below re-trigger this hook)
  if (context?.skipVaultSync) return doc

  // Adapter only works if the Anthropic key is configured
  if (!process.env.ANTHROPIC_API_KEY) return doc

  // Already has a credential -> nothing to do, avoid duplicate credentials
  if (doc.credentialId) return doc

  const update = async (data: Record<string, unknown>) => {
    await req.payload.update({
      collection: 'broker-accounts',
      id: doc.id,
      data,
      overrideAccess: true,
      context: { skipVaultSync: true },
    })
  }

  let vaultId = doc.vaultId as string | undefined

  try {
    const mcp = getMcpConfig(doc.brokerType)

    // No url+token for this broker -> we can't build a valid credential.
    // Do NOT mark 'synced' (that was the original bug). Mark 'error'.
    if (!mcp?.url || !mcp?.token) {
      console.error(
        `[VaultSync] Missing MCP config for broker ${doc.brokerType} (account ${doc.id}). ` +
          `Set the MCP url + token env vars.`,
      )
      await update({ vaultSyncStatus: 'error' })
      return doc
    }

    const adapter = getVaultAdapter()

    const portfolioId =
      typeof doc.portfolio === 'object' && doc.portfolio !== null
        ? doc.portfolio.id
        : doc.portfolio

    // Create the vault if we don't have one yet, tagged with the portfolio
    if (!vaultId) {
      vaultId = await adapter.createVault({
        displayName: `broker-${doc.id}`,
        externalPortfolioId: String(portfolioId),
      })
      // Persist vaultId immediately so a later failure doesn't orphan the vault
      await update({ vaultId })
    }

    // Add the single shared-secret credential for this broker's MCP server
    const credentialId = await adapter.addCredential({
      vaultId,
      mcpServerUrl: mcp.url,
      token: mcp.token,
      displayName: `${doc.brokerType}-${doc.environment ?? 'paper'}`,
    })

    // Only now, with a real credential, mark synced
    await update({ vaultId, credentialId, vaultSyncStatus: 'synced' })
    console.log(
      `[VaultSync] Synced vault ${vaultId} (cred ${credentialId}) for broker account ${doc.id}`,
    )
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown vault sync error'
    console.error(`[VaultSync] FAILED for broker account ${doc.id}:`, message)
    await update({ ...(vaultId ? { vaultId } : {}), vaultSyncStatus: 'error' })
  }

  return doc
}