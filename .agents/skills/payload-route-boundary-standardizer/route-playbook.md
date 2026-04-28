# Route Boundary Playbook

## Goal

Turn routes into boundaries that are easy to read, easy to test, and consistent across the repo.

## The desired route shape

Preferred flow:

1. parse request,
2. validate input,
3. instantiate collaborators,
4. call a use case or boundary service,
5. serialize response.

If the route does more than that, it is probably carrying business logic that belongs elsewhere.

## Repo-specific conventions

Reuse these utilities when possible:

- `src/shared/handlers/index.ts` (hook wrappers: `handleBeforeChangeHook`, `handleAfterChangeHook`, etc.)

When adding new shared route utilities, place them in `src/shared/handlers/`.

## Validation guidance

- Prefer Zod schemas for new request contracts.
- Keep schemas close to the boundary or in a feature-local schema file.
- Validation answers "is the payload well-formed?". Business rules belong deeper.
- Prefer schema modules with `z.infer` types over handwritten DTO interfaces plus manual `typeof` checks.

## Error guidance

- Translate domain or application failures into typed exceptions.
- Avoid scattered `try/catch` blocks unless the route truly needs special translation at a very local step.

## Extraction cues

Extract when the route contains:

- more than one direct query or mutation,
- branching business decisions,
- data massaging that is not HTTP-specific,
- external service calls,
- duplicated filtering logic,
- or enough code that the route no longer reads as a boundary.

## Output expectation

After the refactor, a reviewer should be able to read the route top-to-bottom in under a minute and understand:

- the input contract,
- the delegated use case,
- and the success/error response shape.

## Placement guidance

- feature-local DTOs, presenters, and request context helpers stay under the collection or a feature directory
- `src/shared/**` is reserved for cross-cutting behavior reused by multiple modules

## Final response

Report:

- route paths changed,
- schema or parser added,
- delegated service or use case,
- error-handling changes,
- any remaining logic still in the route and why.
