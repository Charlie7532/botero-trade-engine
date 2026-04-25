# Legacy Prisma Bridge Playbook

## Goal

Move a feature toward Payload without forcing a rewrite of every caller at once.

## Step 1: Inventory reads and writes

For the touched feature, list:

- where reads happen,
- where writes happen,
- which IDs are exposed externally,
- which code paths still depend on Prisma,
- and which code paths already use Payload.

## Step 2: Choose a source of truth

Pick one source of truth for each operation:

- read-only during migration,
- write path,
- lookup by external ID,
- and lookup by internal document ID.

Avoid vague mixed ownership.

## Step 3: Centralize translation

If external callers use legacy IDs but Payload stores numeric document IDs, create one bridge helper or repository boundary to translate between them.

Good examples to look at:

- `src/modules/uploads/infrastructure/payload/payloadUploadFileStore.ts`
- migration utilities under `src/utilities/migrations/**`

## Step 4: Hide migration mechanics

Routes, hooks, and jobs should not each reimplement:

- fallback queries,
- ID parsing,
- or mixed Prisma/Payload branching.

Push that complexity into one bridge boundary.

## Step 5: Minimize dual writes

Dual writes are risky. Only keep them when unavoidable, and when used:

- document the ordering,
- document failure behavior,
- and keep them in one place.

If the task can avoid dual writes by choosing a source of truth plus backfill, prefer that.

## Step 6: Define the exit

Every bridge should state how it gets deleted. Examples:

- remove Prisma fallback after migration script completes,
- remove legacy ID support after consumers switch,
- replace bridge repository with a Payload-only repository.

## Final response

Report:

- source of truth decisions,
- bridge files added or updated,
- duplicated legacy logic removed,
- remaining migration debt,
- and the next cleanup step.
