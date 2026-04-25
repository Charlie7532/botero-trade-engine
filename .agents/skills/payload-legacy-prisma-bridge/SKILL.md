---
name: payload-legacy-prisma-bridge
description: Plan and implement incremental bridges between Prisma-backed legacy flows and Payload-backed domain flows. Use this whenever a feature spans both systems and a big-bang migration is not appropriate.
origin: TridasOS
---

# Payload Legacy Prisma Bridge

Use this skill when a task touches features that still rely on Prisma while Payload is becoming the long-term domain boundary, or when IDs and reads/writes must work across both systems during migration.

This skill is for incremental migration. It helps avoid half-migrated logic scattered across routes and utilities.

## What to produce

- A source-of-truth decision for the touched feature
- A bridge plan for reads, writes, ID translation, and eventual cleanup
- Centralized mapping or repository helpers instead of duplicated conversion logic
- Clear limits on temporary dual-read or dual-write behavior
- Exit criteria for removing the Prisma dependency from that feature

## Project rules

- Pick one source of truth for each use case whenever possible.
- Centralize ID translation and fallback lookup logic.
- Avoid route-level duplication of Prisma and Payload access.
- Do not introduce broad dual-write behavior unless the task truly requires it and the risks are documented.
- Keep bridge code in one feature-local place so it can be removed later.
- If a temporary compatibility facade exists in `src/lib/<feature>/**`, document it as migration debt and remove it once `src/modules/<feature>/**` is the active source of truth.
- If a collection shape changes as part of the migration, also use `supabase-collection-migrations` and remind to run `pnpm payload:generate:types`.

## Workflow

1. Inventory where the feature reads and writes through Prisma vs Payload.
2. Decide the current source of truth for each operation.
3. Centralize ID translation and fallback lookups.
4. Wrap mixed reads or writes behind a repository or bridge service.
5. Keep routes, hooks, and jobs unaware of migration mechanics where possible.
6. Document the removal path for the bridge once the migration is complete.

## Output checklist

- [ ] Source of truth is explicit per operation
- [ ] ID translation is centralized
- [ ] Mixed-mode logic is not duplicated across routes
- [ ] Dual-write behavior is avoided or justified
- [ ] Bridge removal criteria are documented
- [ ] Schema/type follow-ups are called out when relevant

## References

- `.agents/skills/payload-legacy-prisma-bridge/bridge-playbook.md`
- `src/lib/prisma.ts`
- `src/modules/uploads/infrastructure/payload/payloadUploadFileStore.ts`
- `src/app/api/v1/**`
- `src/app/api/v2/**`
- `src/utilities/migrations/**`
