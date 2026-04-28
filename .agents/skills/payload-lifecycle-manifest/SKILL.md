---
name: payload-lifecycle-manifest
description: Create or normalize Payload lifecycle manifests and shared hook handlers so collection behavior is explicit, wrapped, and easy to trace. Use this whenever a task changes hooks, lifecycle composition, or shared Payload handlers.

---

# Payload Lifecycle Manifest

Use this skill when a task touches hooks in `src/collections/**`, adds side-effects to a collection, introduces shared hook wrappers, or makes it hard to answer "what happens when this document is created, updated, or deleted?".

This skill is for discovery, shared handler standardization, hook normalization, and lifecycle composition. It is not the primary skill for deep business-logic extraction; when a hook contains real orchestration, hand off to `payload-hook-first-use-case`.

## What to produce

- A `lifecycle.ts` file colocated with the collection, or updated if it already exists
- Shared generic handlers under `src/shared/handlers/**` when the repo is missing them or the touched task changes the wrapper standard
- Named hook exports grouped by lifecycle stage (`beforeValidate`, `beforeChange`, `afterChange`, `beforeDelete`, `afterDelete`, operation hooks when needed)
- A short manifest comment that lists execution order, guards, and visible side-effects
- A simplified collection `index.ts` that imports hook composition instead of burying behavior inline
- Follow-up notes for hooks that should be extracted into rules/use cases

## Project rules

- Prefer one obvious lifecycle entrypoint per collection.
- Prefer generic cross-cutting hook and endpoint handlers in `src/shared/handlers`.
- Prefer named wrapped hooks over inline anonymous hook functions.
- Do not change behavior just to reorganize code unless the task explicitly asks for it.
- If wrapper utilities do not exist yet, create them in `src/shared/handlers` and keep naming consistent.
- Keep collection-specific behavior out of shared handlers; shared code is only for generic wrappers and adapter boundaries.
- If a hook receives `req.payload`, prefer request-scoped feature dependencies built from that instance instead of bootstrapping a new Payload client.
- Keep feature-specific hook orchestration, presenters, and DTO helpers inside `src/modules/<feature>/**`, not `src/shared/**`.
- If a hook has branching business logic, hidden side-effects, or multi-entity coordination, flag it for `payload-hook-first-use-case`.
- If the task changes collection schema, remind to run `pnpm payload:generate:types`.

## Workflow

1. Read the target collection and any related hook files.
2. Inventory hooks by stage, operation, guards, side-effects, and current shared wrapper usage.
3. Create or update shared handlers in `src/shared/handlers` when the wrapper standard is missing or inconsistent.
4. Name each hook for its real responsibility, not its technical event alone.
5. Create or update `lifecycle.ts` with grouped exports in execution order.
6. Replace inline hook arrays in the collection with a single imported lifecycle composition where practical.
7. Preserve behavior, guard order, error semantics, and return values.
8. Report any hook that still contains business logic and should move to a use case.

## Output checklist

- [ ] Lifecycle composition exists in one obvious file
- [ ] Shared handlers live in `src/shared/handlers` when introduced or updated
- [ ] Hooks are named and grouped by stage
- [ ] Guards and side-effects are documented in the manifest comment
- [ ] Collection config is easier to scan after the change
- [ ] Behavior-preserving changes are kept separate from deeper refactors
- [ ] Schema follow-ups are called out when relevant

## References

- `.agents/skills/payload-lifecycle-manifest/manifest-playbook.md`
- `src/collections/**`
- `src/shared/handlers/**`
- `src/payload.config.ts`
