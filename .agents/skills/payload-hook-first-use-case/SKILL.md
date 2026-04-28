---
name: payload-hook-first-use-case
description: Extract business logic from Payload hooks, routes, and jobs into rules, use cases, and adapters. Use this whenever a hook or endpoint mixes orchestration, persistence, and side-effects.

---

# Payload Hook-First Use Case

Use this skill when a Payload hook, Next.js route, job handler, or helper mixes business decisions with direct `payload` or external service calls.

This skill applies the repo's CLEAN direction incrementally: thin adapters at the edge, business rules in pure functions, orchestration in use cases, and infrastructure behind ports or repository seams.

## What to produce

- Extracted domain rules for pure predicates and transformations
- One or more use cases for orchestration and side-effects
- Repository or port interfaces where the domain should not know about Payload
- Thin adapters in hooks, routes, or jobs that instantiate dependencies and call the use case

## Project rules

- If a hook or route has an `if` that expresses a business decision, try to move that decision into a rule or use case.
- The domain or use-case layer must not import Next.js request objects, Payload request objects, or UI code.
- Prefer explicit side-effects inside the use case over hidden side-effects buried in hooks.
- Integration adapters (for example n8n/Cloudinary HTTP clients) must be transport-only; they should not query repositories or collections directly.
- Use cases must gather required domain data and build integration payloads before calling gateway/adapters.
- Use the smallest stable extraction that improves clarity; do not do a big-bang folder rewrite.
- If a long-lived module is being established, prefer `src/modules/<feature>/domain/**` and `src/modules/<feature>/infrastructure/**`.
- Reusable code that only belongs to one feature stays inside `src/modules/<feature>/**`; only move code to `src/shared/**` when it is truly cross-cutting across multiple modules.
- Prefer classes with `execute()` for use cases and keep controllers/hooks/endpoints as thin functions or factories.
- Prefer Zod schemas for boundary DTOs instead of manual validation logic.
- If the runtime already provides `req.payload`, inject that instance into feature dependencies and repositories instead of bootstrapping a new Payload client.
- Avoid leaving long-term facades; once a feature is stable, remove transitional layers.

## Workflow

1. Read the edge adapter first: hook, route, or job handler.
2. Split the code into pure rules, orchestration, persistence, and side-effects.
3. Move pure logic into rules.
4. Move orchestration into a use case with injected collaborators.
5. Hide Payload access behind repositories, ports, or feature services.
6. Reduce the edge adapter to parsing, instantiation, and response wiring.
7. Verify that admin, API, and background flows can now share the same use case when relevant.

## Output checklist

- [ ] Pure rules are separated from I/O
- [ ] Orchestration lives in a use case or equivalent application service
- [ ] Direct data access is isolated behind a clear boundary
- [ ] Hook, route, or job adapter is visibly thinner after the change
- [ ] Side-effects are explicit and testable
- [ ] Incremental placement is documented when the final module layout is not created yet

## References

- `.agents/skills/payload-hook-first-use-case/extraction-playbook.md`
- `src/app/api/**`
- `src/collections/**`
