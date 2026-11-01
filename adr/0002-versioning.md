# ADR-0002: Contract versioning and compatibility

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` G7 and §7 Constraints; `notes/config.md` C1

## Context
Implementations, persisted checkpoints, and recorded traces all depend on the contract. Changes must be predictable, and two different things are versioned: the spec itself and individual configuration artifacts.

## Decision
From prior decisions:
- The contract is versioned; changes are additive unless a major version says otherwise (G7).
- Every persisted or emitted document carries `schemaVersion` (§7).
- **Configuration artifacts** use plain integer versions, referenced exactly (`id@version`); no ranges (C1).

**Added in this ADR (approved 2026-10-31):**
- Spec releases use semantic versioning (`MAJOR.MINOR.PATCH`):
  - **Minor:** additive only — new optional fields, new schemas, new fixtures for new behaviour.
  - **Major:** anything that can break a conforming implementation or invalidate stored data.
  - **Patch:** clarifications and fixture corrections that do not change intended behaviour.
- CI fails on a schema diff that would be breaking without a major version bump.
- Major versions must provide a migration path for persisted checkpoints (detail deferred to the storage ports spec).

## Consequences
- Implementations can state exactly which contract version they conform to.
- Checkpoints and traces from older minor versions remain readable within a major version.

## Alternatives considered
- **Calendar versioning** — conveys age, not compatibility.
- **Semver for artifacts** — ranges are not used, so semver adds nothing over integers.
