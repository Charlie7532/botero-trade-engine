# Envelope Encryption Sprint Plan

> Companion document to [docs/envelope-encryption-migration-plan.md](docs/envelope-encryption-migration-plan.md)
> Purpose: turn strategy into executable tickets and daily delivery checkpoints
> Scope: Broker credential envelope encryption migration

---

## Sprint Summary

- Duration: 5 to 7 working days
- Team shape: 1 backend engineer + 1 reviewer (part-time)
- Goal: production-ready envelope encryption with safe migration path and rollback

---

## Delivery Tracks

### Track A: Crypto and KMS integration

- A1: KMS adapter implementation
- A2: Envelope encrypt/decrypt service
- A3: Versioned decrypt compatibility (`v1` and `v2`)

### Track B: Collection and lifecycle wiring

- B1: BrokerCredentials schema metadata for envelope keys
- B2: Lifecycle update for v2 write path
- B3: Access and masking integrity checks

### Track C: Migration and operations

- C1: Backfill script with dry-run mode
- C2: Monitoring, metrics, and alerts
- C3: Rollback and incident runbook

---

## Day-by-Day Execution Board

## Day 1: Foundation

### Ticket EENC-01: KMS contract and adapter skeleton

- Outcome: stable provider interface for wrap/unwrap operations
- Files (planned):
  - `src/shared/infrastructure/kms/*`
  - `src/shared/domain/encryption.ts`
- Acceptance:
  - adapter has unit tests for happy path and deny path
  - no secret values logged

### Ticket EENC-02: Envelope payload model

- Outcome: canonical model for envelope metadata and ciphertext bundles
- Files (planned):
  - `src/shared/domain/encryption.ts`
- Acceptance:
  - includes `wrappedDek`, `kekKeyId`, `kekKeyVersion`, `encryptionVersion`
  - serialization format documented in code comments

---

## Day 2: Write Path

### Ticket EENC-03: BrokerCredentials schema extension

- Outcome: schema supports envelope metadata storage
- Files (planned):
  - `src/collections/BrokerCredentials/fields.ts`
  - `src/payload-types.ts` (generated)
- Acceptance:
  - metadata fields added and hidden/read-protected where needed
  - `pnpm generate` updates types cleanly

### Ticket EENC-04: v2 envelope encryption on create

- Outcome: new credential sets are always written in envelope format
- Files (planned):
  - `src/collections/BrokerCredentials/lifecycle.ts`
  - `src/collections/BrokerCredentials/domain/useCases/*`
- Acceptance:
  - `encryptionVersion` is set to `v2-envelope`
  - plaintext fields removed before persistence

---

## Day 3: Compatibility and Safety

### Ticket EENC-05: dual-read decrypt path (`v1` + `v2`)

- Outcome: application can decrypt both legacy and envelope records
- Files (planned):
  - `src/shared/domain/encryption.ts`
  - decryption call sites used by execution/runtime services
- Acceptance:
  - version routing covered by tests
  - no behavior regression for legacy records

### Ticket EENC-06: strict failure semantics

- Outcome: decrypt failures are explicit and observable
- Files (planned):
  - `src/shared/domain/encryption.ts`
  - lifecycle/use-case boundaries
- Acceptance:
  - invalid auth tag and wrong key produce deterministic typed errors
  - no silent fallback from `v2` to `v1`

---

## Day 4: Migration Tooling

### Ticket EENC-07: backfill migrator (dry-run + apply)

- Outcome: safe migration utility for existing records
- Files (planned):
  - `scripts/migrate_broker_credentials_to_envelope.ts` (or equivalent)
- Acceptance:
  - dry-run prints migration counts only
  - apply mode supports batching and resume
  - migration is idempotent for already migrated rows

### Ticket EENC-08: migration observability

- Outcome: actionable metrics and logs during backfill
- Files (planned):
  - migration script + logging hooks
- Acceptance:
  - success/failure counters
  - list of failed record ids without secret values

---

## Day 5: Validation and Rollout

### Ticket EENC-09: staging drill

- Outcome: end-to-end validation before production
- Steps:
  - create new credential set (`v2`)
  - decrypt in runtime path
  - rotate credential set and verify active-set behavior
  - run backfill on staging snapshot
- Acceptance:
  - all smoke checks pass

### Ticket EENC-10: production rollout and rollback rehearsal

- Outcome: controlled production cutover plan approved
- Deliverables:
  - deployment checklist
  - rollback checklist
  - owner on-call assignment
- Acceptance:
  - rollback tested in staging
  - risk sign-off complete

---

## Optional Days 6-7 (if needed)

### Ticket EENC-11: performance tuning

- focus: KMS latency and caching strategy

### Ticket EENC-12: hardening and policy review

- focus: IAM tightening, alarm thresholds, runbook quality

---

## Ticket Priority Matrix

- P0: EENC-03, EENC-04, EENC-05, EENC-07
- P1: EENC-01, EENC-02, EENC-06, EENC-09
- P2: EENC-08, EENC-10, EENC-11, EENC-12

---

## Definition of Done

- New writes use `v2-envelope`
- Legacy `v1` remains decryptable during migration window
- Backfill completed with zero unrecoverable rows
- No plaintext secrets in logs, metrics, or admin UI
- One active credential set per broker account still enforced
- Runbooks tested and stored in docs

---

## Suggested Owners

- Security/Crypto owner: KMS and encryption primitives
- Platform owner: lifecycle wiring and schema updates
- Ops owner: migration execution and monitoring

---

## Commands and Checkpoints

- Type regeneration after schema changes:
  - `pnpm generate`
- Validate no new type issues:
  - use editor Problems panel / CI checks
- Migration dry-run first, then apply in batches

---

## Notes

- Do not store plaintext DEKs in database
- Do not remove `v1` decrypt support until migration is complete and verified
- Keep this document synchronized with [docs/envelope-encryption-migration-plan.md](docs/envelope-encryption-migration-plan.md)
