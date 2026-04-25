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

- `src/shared/handlers/handlerRoute.ts`
- `src/shared/handlers/handlePayloadEndpoint.ts`
- `src/shared/kernel/exceptions.ts`
- `src/lib/parseJsonBody.ts`

Use the Payload custom uploads endpoints under `src/modules/uploads/interface/payload/endpoints/` as the local example of a thinner route style and `src/app/api/v1/leads/route.ts` as a typical extraction candidate.

## Validation guidance

- Prefer Zod schemas for new request contracts.
- Keep schemas close to the boundary or in a feature-local schema file.
- Validation answers "is the payload well-formed?". Business rules belong deeper.
- Prefer schema modules with `z.infer` types over handwritten DTO interfaces plus manual `typeof` checks.

## Error guidance

- Translate domain or application failures into typed exceptions.
- Let `handlerRoute` produce the final HTTP response when possible.
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

- feature-local DTOs, presenters, and request context helpers stay under `src/modules/<feature>/**`
- `src/shared/**` is reserved for cross-cutting behavior reused by multiple modules
- if a feature already lives in `src/modules/<feature>/**`, treat any `src/lib/<feature>/**` path as temporary migration debt and remove it when safe

## Final response

Report:

- route paths changed,
- schema or parser added,
- delegated service or use case,
- error-handling changes,
- any remaining logic still in the route and why.
