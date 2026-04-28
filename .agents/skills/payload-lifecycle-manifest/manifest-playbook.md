# Lifecycle Manifest Playbook

## Goal

Make collection behavior discoverable without changing the domain model. After this refactor, a reviewer should be able to open one file and answer:

- what runs on create,
- what runs on update,
- what runs on delete,
- what guards short-circuit the hook,
- and which side-effects happen.

## Preferred file placement

- Generic wrappers and adapter controllers: `src/shared/handlers/index.ts`
- Current collection default: colocate `lifecycle.ts` next to `src/collections/<CollectionName>/index.ts`
- Target architecture when a feature module exists: `src/modules/<feature>/interface/lifecycle.ts`

Use the smallest move that makes the current task clearer.

## Step 1: Inventory the current lifecycle

For each collection, list:

- inline hook arrays in `index.ts`
- imported hook functions
- operation guards (`create`, `update`, `delete`)
- implicit side-effects (events, related record updates, external API calls)
- `overrideAccess`, `req.context`, or skip flags that affect behavior

If the collection has no hooks yet, decide whether a lifecycle manifest is still useful for future clarity.

## Step 2: Name hooks by responsibility

Bad names:

- `afterChangeHook`
- `beforeChangeHandler`
- `hook1`

Better names:

- `assignAccountOnCreateHook`
- `syncUploadSessionProgressHook`
- `emitLeadQualifiedEventHook`

The name should explain why the hook exists.

## Step 3: Normalize structure

Preferred shape:

```ts
export const leadLifecycle = {
  beforeValidate: [],
  beforeChange: [assignAccountOnCreateHook],
  afterChange: [syncLeadStatusHook, emitLeadCreatedEventHook],
  beforeDelete: [],
  afterDelete: [],
};
```

If hook wrappers exist, use them consistently. Preferred wrapper naming:

- `handleBeforeValidateHook`
- `handleBeforeChangeHook`
- `handleAfterChangeHook`
- `handleBeforeDeleteHook`
- `handleAfterDeleteHook`
- `handleBeforeOperationHook`
- `handleAfterOperationHook`

If the repo does not yet have wrappers, create them in `src/shared/handlers`.

## Step 4: Standardize shared handlers

When the repo is missing generic wrappers, introduce them under `src/shared/handlers`.

Recommended files:

- `src/shared/handlers/index.ts` (already exists with `handleBeforeChangeHook`, `handleAfterChangeHook`, `handleAfterDeleteHook`, `handleAfterReadHook`, `handleGlobalAfterChangeHook`)

Keep them generic. Do not move collection-specific behavior into shared code.

When the hook runtime already provides `req.payload`, inject that instance into feature dependencies or repositories. Avoid calling `getPayload()` again inside hooks unless there is no injected Payload context.

### Error and return semantics

- `handleBeforeValidateHook` and `handleBeforeChangeHook`
  - run operation filters and guards first
  - return `param.data` when skipped
  - log and re-throw on error so the write aborts
- `handleBeforeDeleteHook`
  - return early when guarded out
  - log and re-throw on error so the delete aborts
- `handleAfterChangeHook`
  - return `param.doc` when skipped or when a non-critical side-effect fails
- `handleAfterDeleteHook`
  - log and swallow non-critical side-effect failures

Use `req.payload.logger ?? console` semantics for logging.

Shared placement rule:

- `src/shared/**` only for cross-cutting code used by multiple modules
- feature-local schemas, presenters, context helpers, and orchestration remain inside the collection or a feature directory

## Step 5: Add manifest documentation

At the top of `lifecycle.ts`, add a short comment that captures:

- stage order,
- major guards,
- side-effects,
- and any known caveats.

Keep it short and operational. It should help discovery, not become long-form docs.

## Step 6: Simplify the collection file

The collection file should focus on:

- schema,
- admin config,
- access,
- and a single lifecycle import.

If the collection becomes more complicated after introducing the manifest, stop and reduce the scope.

## Step 7: Flag extraction candidates

Move to `payload-hook-first-use-case` when a hook:

- has branching business logic,
- coordinates multiple entities,
- calls external services,
- emits events plus writes data,
- or contains logic that should be shared by admin, jobs, and API.

## Final response

Report:

- manifest path,
- shared handler paths introduced or updated,
- hooks grouped by stage,
- behavior preserved,
- extraction candidates,
- schema/type follow-ups if relevant.
