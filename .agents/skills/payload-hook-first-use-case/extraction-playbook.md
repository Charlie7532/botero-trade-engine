# Hook-First Use Case Extraction Playbook

## Goal

Keep Payload as the execution entrypoint when possible, but move business logic out of hooks and routes so it can be reused and tested.

## Decision guide

### Move code into a rule when it is:

- a predicate,
- a transition check,
- a limit or threshold rule,
- a data transformation,
- or any function that can stay pure.

### Move code into a use case when it:

- coordinates multiple repositories,
- decides whether to perform side-effects,
- emits events,
- enqueues jobs,
- or applies business rules across multiple steps.

### Keep code in an adapter when it is:

- parsing a request,
- reading route params,
- converting Payload documents to use-case input,
- instantiating repositories,
- returning HTTP responses,
- or forwarding the final result.

## Preferred layering

Target architecture when the task warrants it:

```text
src/modules/<feature>/
  domain/
    rules/
    ports/
  application/
    use-cases/
    dto/
  interface/
    presenters/
    hooks/
    api/
    jobs/
  infrastructure/
    payload/
```

Incremental fallback in the current repo:

```text
src/lib/<feature>/
  rules.ts
  useCases.ts
  repositories.ts
```

Use this fallback only as a temporary migration step. Once `src/modules/<feature>/**` exists, remove the `src/lib/<feature>/**` facade.

## Payload-specific guidance

- Hooks should be thin adapters, not the place where the system decides business outcomes.
- Prefer one shared use case for admin, API, and job execution paths.
- If API and admin should behave the same, route code should flow through Payload Local API or through the same extracted use case.
- If the edge runtime already provides `req.payload`, pass that instance into feature-scoped dependencies/repositories instead of calling `getPayload()` again.

## Repository and port guidance

Create a repository or port when:

- the domain should not know about Payload types or method names,
- the logic may need to work across Payload and Prisma during migration,
- or repeated data access patterns are cluttering edge code.

Do not add ports just for ceremony. Simple one-off CRUD inside a thin infrastructure helper is fine when no additional boundary is needed.

Repository placement rules:

- feature-specific repositories stay in `src/modules/<feature>/infrastructure/**`
- cross-cutting wrappers only go in `src/shared/**` when reused across multiple modules
- request parsing helpers such as `getClientIp` stay in `interface/http/**`, not in infrastructure

## Side-effects

Prefer this order inside a use case:

1. validate inputs and state,
2. fetch required entities,
3. apply business decision,
4. persist state changes,
5. emit events / enqueue jobs / call external services.

Keep side-effects explicit in code and in naming.

## Testing guidance

The extraction is good when the use case can be exercised with fake collaborators and no Payload runtime.

## Final response

Report:

- extracted rules,
- extracted use cases,
- repositories or ports added,
- adapters kept thin,
- remaining technical debt if the migration is only partial.
- whether any `req.payload` boundary can replace local Payload bootstrap.
