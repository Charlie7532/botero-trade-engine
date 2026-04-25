---
name: payload-route-boundary-standardizer
description: Standardize Next.js API routes around clear boundaries, typed errors, and thin adapters for Payload-backed features. Use this whenever a route mixes validation, business logic, and persistence.
origin: TridasOS
---

# Payload Route Boundary Standardizer

Use this skill when adding or refactoring routes in `src/app/api/**`, especially when a route is long, mixes direct data access with business logic, or returns inconsistent error shapes.

This skill makes routes act as boundaries: parse input, validate, instantiate collaborators, call a use case or repository boundary, and serialize the response.

## What to produce

- Thin route handlers that focus on HTTP concerns only
- Input validation isolated at the boundary, preferably with Zod
- Consistent error handling through `src/shared/handlers/handlerRoute.ts` and `src/shared/kernel/exceptions.ts`
- Business logic moved into feature services, repositories, or use cases
- Stable request and response shapes that do not leak infrastructure details

## Project rules

- Routes should parse, validate, delegate, and respond. They should not carry large business workflows.
- Prefer `handlerRoute` for consistent error translation.
- Prefer importing route adapters from `src/shared/handlers` for new code.
- Prefer importing control exceptions from `src/shared/kernel/exceptions.ts`.
- Prefer typed control exceptions over ad hoc `return NextResponse.json({ error: ... })` branches scattered through the file.
- Prefer dedicated request parsers or schemas over inline validation.
- Use Zod for new boundary schemas when it fits the touched area; keep validation isolated even if the task only introduces a small parser.
- Keep controllers as thin functions or factories; prefer classes with `execute()` for use cases instead.
- Keep presenters as pure feature-local functions; do not move them to `src/shared/**` unless multiple modules reuse them.
- If a route manipulates Payload collections, prefer Payload Local API directly or through repositories that wrap it.
- Adapters/gateways used by routes should be transport clients only; data fetching and payload shaping belong in use cases.
- For uploads, standardize on exactly three repository ports: `AccountRepository`, `UploadFilesRepository`, and `UploadSessionRepository`.
- Adapters/gateways used by routes should be transport clients only; data fetching and payload shaping belong in use cases.
- For uploads, standardize on exactly three repository ports: `AccountRepository`, `UploadFilesRepository`, and `UploadSessionRepository`.

## Workflow

1. Read the route and identify HTTP concerns vs business logic.
2. Isolate request parsing and validation.
3. Move business logic into a use case, service, or repository boundary.
4. Standardize exceptions and response mapping.
5. Keep the final route small enough to scan quickly.
6. Verify behavior, status codes, and error shape are preserved or intentionally improved.

## Output checklist

- [ ] Route delegates most non-HTTP work
- [ ] Validation is isolated at the boundary
- [ ] Error handling is consistent and typed
- [ ] Persistence and orchestration moved out of the route where appropriate
- [ ] Response shape is explicit and stable
- [ ] Follow-up extractions are called out if the task stops short of a full refactor

## References

- `.agents/skills/payload-route-boundary-standardizer/route-playbook.md`
- `src/shared/handlers/handlerRoute.ts`
- `src/shared/handlers/handlePayloadEndpoint.ts`
- `src/shared/kernel/exceptions.ts`
- `src/lib/parseJsonBody.ts`
- `src/app/api/**`
