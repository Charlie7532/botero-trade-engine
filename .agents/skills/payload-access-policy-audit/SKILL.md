---
name: payload-access-policy-audit
description: Audit and improve Payload access policy, tenant scoping, and overrideAccess usage. Use this whenever a task changes roles, collection access, or trusted data-access paths.
origin: TridasOS
---

# Payload Access Policy Audit

Use this skill when a task touches `access` blocks in collections, role or membership helpers, account-scoped reads and writes, or any code path using `overrideAccess: true`.

This skill helps keep multi-tenant data access explicit, least-privilege, and consistent between collections, routes, and infrastructure helpers.

## What to produce

- An actor/resource access matrix for the touched feature
- Safe collection access rules and helper reuse where appropriate
- A review of `overrideAccess: true` usage and whether it belongs in trusted infrastructure code only
- Any route or repository changes needed to preserve tenant isolation
- Clear notes for admin vs super-admin vs account-member behavior

## Project rules

- Prefer collection access rules as the first line of defense.
- Use `overrideAccess: true` only in trusted infrastructure code with an explicit reason.
- Keep account membership and tenant scoping logic centralized when possible.
- Do not silently widen access while refactoring other behavior.
- Make role-based exceptions explicit in code and in the final summary.
- If access relies on a relationship field, verify the field still exists and is named correctly after schema changes.

## Workflow

1. Read the touched collection access rules and supporting helpers in `src/access/**`.
2. Inspect any route, repository, or helper that bypasses access.
3. Build the minimal actor matrix for the task: public, authenticated, self, account member, account admin, admin, super-admin.
4. Align collection access, route guards, and infrastructure access decisions.
5. Tighten or document `overrideAccess` usage.
6. Verify the final behavior is tenant-safe and intentionally scoped.

## Output checklist

- [ ] Actor/resource matrix is explicit
- [ ] Collection access and helper usage are aligned
- [ ] `overrideAccess` usage is justified or reduced
- [ ] Tenant scoping is preserved
- [ ] Admin and super-admin behavior is explicit
- [ ] Any risky widening of access is called out clearly

## References

- `.agents/skills/payload-access-policy-audit/access-playbook.md`
- `src/access/**`
- `src/collections/**`
- `src/lib/auth/**`
- `src/modules/uploads/infrastructure/payload/payloadUploadFileStore.ts`
