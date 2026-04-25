# Access Policy Playbook

## Goal

Make it obvious who can read, create, update, and delete each resource involved in the task, and make sure trusted bypasses stay small and deliberate.

## Step 1: Map actors

At minimum, evaluate these actors when relevant:

- public
- authenticated user
- current user / self
- account member
- account admin
- platform admin
- super-admin

Only include the actors that matter for the touched feature, but do not skip an elevated role if the code references it.

## Step 2: Map boundaries

Review access decisions across three places:

1. collection access in `src/collections/**`
2. helper logic in `src/access/**`
3. trusted infrastructure or route code using `overrideAccess: true`

If the same rule is reimplemented in multiple places, prefer one clear source of truth.

## Step 3: Audit `overrideAccess`

`overrideAccess: true` is acceptable when:

- it lives in infrastructure code,
- the caller is already trusted,
- the method is performing system work rather than user-authorized access,
- and tenant scoping is still enforced explicitly if needed.

It is risky when:

- it appears directly in route handlers,
- it is used for convenience rather than necessity,
- or it bypasses account scoping with no compensating guard.

## Step 4: Keep scoping logic explicit

For tenant-scoped data:

- make the account relationship or ownership field explicit,
- validate that membership helpers match the actual schema,
- and keep field names in sync with collection configuration.

Use `src/access/accountMember.ts` and related helpers as the first place to check for drift.

## Step 5: Report behavior, not just code

The final response should say who can do what after the change, not only which files changed.

## Final response

Report:

- touched actors,
- affected collections/routes/helpers,
- any `overrideAccess` findings,
- access changes made,
- residual risk if a broader audit is still needed.
