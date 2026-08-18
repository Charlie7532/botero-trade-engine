# Vault Sync Architecture & Cascade Hooks

## Summary

Implements a generic, provider-agnostic credential vault infrastructure and cascade synchronization hooks for the Botero Trade Engine. This PR establishes the secure credential management layer that enables Managed Agent Sessions to access broker credentials at runtime without persisting secrets in plaintext.

## Architecture Changes

```mermaid
graph TD
    subgraph "Shared Domain Layer"
        VP["IVaultAdapter<br/>(Port Interface)"]
    end

    subgraph "Shared Infrastructure Layer"
        CVA["ClaudeVaultAdapter"]
        VF["vaultFactory.ts"]
    end

    subgraph "Collections"
        subgraph "ProjectVaults"
            PV["ProjectVaults Collection<br/>(Admin-only metadata)"]
        end

        subgraph "BrokerAccounts"
            BA_F["fields.ts<br/>+ vaultId, credentialId,<br/>vaultSyncStatus"]
            BA_H["syncVaultOnSave<br/>(afterChange hook)"]
        end

        subgraph "AgentSkills"
            AS_F["fields.ts<br/>+ lastSyncedAt,<br/>syncedBotCount"]
            AS_H["resyncDependentBots<br/>(afterChange hook)"]
        end

        subgraph "McpServers"
            MCP_F["fields.ts<br/>+ credentialScope,<br/>platformApiKeyEnvVar,<br/>lastSyncedAt"]
            MCP_H["resyncDependentBots<br/>(afterChange hook)"]
        end

        subgraph "Bots"
            BOT_H["syncAgentOnSave<br/>+ broker MCP injection<br/>+ vaultId capture"]
        end
    end

    subgraph "API Layer"
        CHAT["POST /api/agent/[slug]/chat<br/>Managed Agent Sessions<br/>+ vault ID injection"]
    end

    VP --> CVA
    VF --> CVA
    BA_H --> VF
    AS_H -->|"re-save"| BOT_H
    MCP_H -->|"re-save"| BOT_H
    CHAT -->|"resolve vaultIds"| PV
    CHAT -->|"resolve vaultIds"| BA_F
    BOT_H -->|"inject broker MCP"| BA_F

    style VP fill:#4a9eff,color:#fff
    style CVA fill:#6c5ce7,color:#fff
    style VF fill:#6c5ce7,color:#fff
    style PV fill:#00b894,color:#fff
    style BA_H fill:#fdcb6e,color:#333
    style AS_H fill:#fdcb6e,color:#333
    style MCP_H fill:#fdcb6e,color:#333
    style BOT_H fill:#e17055,color:#fff
    style CHAT fill:#d63031,color:#fff
```

## Credential Flow

```mermaid
sequenceDiagram
    participant Admin as Admin UI
    participant BA as BrokerAccounts
    participant VF as vaultFactory
    participant VA as ClaudeVaultAdapter
    participant Chat as Chat API
    participant Claude as Claude API

    Admin->>BA: Save broker credentials
    BA->>BA: Encrypt (beforeChange)
    BA->>VF: syncVaultOnSave (afterChange)
    VF->>VA: createVault() / storeSecret()
    VA-->>BA: vaultId stored on doc

    Note over Chat: User sends message

    Chat->>BA: Resolve broker vaultId
    Chat->>Claude: Managed Agent Session<br/>+ vault_ids[]
    Claude-->>Chat: Streaming response
```

## Files Changed

### New Files
| File | Purpose |
|------|---------|
| `src/shared/domain/ports/vaultPort.ts` | `IVaultAdapter` interface — provider-agnostic vault contract |
| `src/shared/infrastructure/vault/claudeVaultAdapter.ts` | Claude Vault HTTP API adapter |
| `src/shared/infrastructure/vaultFactory.ts` | Factory returning adapter based on `VAULT_PROVIDER` env var |
| `src/collections/ProjectVaults/fields.ts` | Field definitions for project-wide vault metadata |
| `src/collections/ProjectVaults/index.ts` | Admin-only collection config |
| `src/collections/BrokerAccounts/infrastructure/hooks/syncVaultOnSave.ts` | Vault sync hook for broker credentials |
| `src/collections/AgentSkills/infrastructure/hooks/resyncDependentBotsOnSkillChange.ts` | Cascade resync: skill change → re-save dependent bots |
| `src/collections/McpServers/infrastructure/hooks/resyncDependentBotsOnMcpChange.ts` | Cascade resync: MCP change → re-save dependent bots |

### Modified Files
| File | Change |
|------|--------|
| `src/payload.config.ts` | Registered `ProjectVaults` collection |
| `src/collections/BrokerAccounts/fields.ts` | Added generic vault fields (`vaultId`, `credentialId`, `vaultSyncStatus`); removed Claude-specific fields |
| `src/collections/BrokerAccounts/lifecycle.ts` | Wired `syncVaultOnSave` into `afterChange` |
| `src/collections/AgentSkills/fields.ts` | Added `lastSyncedAt`, `syncedBotCount` for sync tracking |
| `src/collections/AgentSkills/index.ts` | Wired cascade resync hook into `afterChange` |
| `src/collections/McpServers/fields.ts` | Added `credentialScope`, `platformApiKeyEnvVar`, `linkedBrokerType`, `lastSyncedAt`, `syncedBotCount` |
| `src/collections/McpServers/index.ts` | Wired cascade resync hook into `afterChange` |
| `src/collections/McpServers/domain/rules/mcpRules.ts` | Updated MCP categories (platform/portfolio credential scopes) |
| `src/collections/BrokerAccounts/domain/rules/portfolioRules.ts` | Added `BROKER_MCP_ENDPOINTS` mapping and `hasBrokerMcp` helper |
| `src/collections/Bots/infrastructure/hooks/syncAgentOnSave.ts` | Injects broker-specific MCP endpoint + captures `vaultId` from active BotAssignment |
| `src/app/api/agent/[slug]/chat/route.ts` | Refactored to support Managed Agent Sessions with vault ID injection (fallback to Messages API) |

### Bug Fixes (Pre-existing)
| File | Fix |
|------|-----|
| `src/providers/Auth/index.tsx` | Removed `isOperator` role (doesn't exist in this project) |
| `src/providers/Auth/server.ts` | Removed `isOperator` from server session |
| `src/app/(frontend)/(settings)/portafolio/[slug]/settings/actions.ts` | Added `draft: false` + `user` field to satisfy regenerated Payload types |
| `src/collections/Portfolios/infrastructure/PayloadPortfolioCreator.ts` | Added `draft: false`, `status: 'active'`, `Number(ownerId)` |
| `src/components/AgentChat/index.tsx` | Fixed HeroUI v3 props (`variant="soft"`, removed `color`/`radius`) |
| `src/scripts/seedAgentSkills.ts` | Added non-null assertions on regex match groups |

### Architecture Cleanup
| Action | Details |
|--------|---------|
| **Deleted** `src/collections/Domain/` | Shared vault port moved → `src/shared/domain/ports/` |
| **Deleted** `src/collections/Infrastructure/` | Shared vault adapter moved → `src/shared/infrastructure/vault/` |
| **Deleted** `src/collections/McpServers/lifecycle.ts` | Hooks now wired directly in collection `index.ts` |

## Design Decisions

1. **Generic vault fields** — All vault-related database fields use provider-agnostic names (`vaultId` instead of `claudeVaultId`) to support future migration to any vault service.
2. **Two-tier MCP credentials** — Platform MCPs read from env vars (no vault); Portfolio MCPs use per-account vaults.
3. **Cascade resync pattern** — AgentSkills and McpServers changes automatically re-save dependent Bots, triggering `syncAgentOnSave` to rebuild the Claude agent config.
4. **Managed Agent Sessions** — Chat API uses vault IDs at session creation time; Claude resolves the secrets internally. No plaintext secrets leave the vault.
5. **Clean Architecture compliance** — Shared domain/infrastructure code lives in `src/shared/`, not inside `src/collections/`.

## Testing

- ✅ Production build passes (`pnpm build` — exit code 0)
- ✅ TypeScript strict checking passes
- ✅ Zero stale imports referencing deleted folders
