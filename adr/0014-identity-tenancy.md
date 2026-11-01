# ADR-0014: Principal identity and tenant isolation

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `notes/security.md` §5–6; `domain.md` §4 and invariants 1, 11, 12

## Context
Agents act on behalf of people in a HIPAA-covered setting. Every action must be attributable, every record isolated per tenant, and delegation must never widen what an agent may do.

## Decision
- Every session has a **principal** (subject, tenant, roles, attributes, assurance level), supplied by the host. agentry never authenticates.
- The principal is immutable for the life of the session, including across `resume`. Unattended runs use an explicit service principal; there is no anonymous mode.
- Principal attributes are available to CEL rules.
- **Delegation** inherits the caller's principal; the sub-agent's scope is the intersection of the caller's runtime scope and its own allowlist.
- Tool credentials are obtained per principal where possible. Tools using a shared credential declare `credentialMode: service` and must enforce the principal's rights themselves.
- Escalation reviewers are separate principals, recorded with their decisions.
- Every storage port is **tenant-scoped**: checkpoints, idempotency keys, traces, audit, blobs, vectors. Wrong-tenant access behaves as not found. Retrieval filters by tenant and principal rights inside the port. Caches are keyed by tenant. No cross-tenant operations in 1.0.

## Consequences
- Attribution and isolation are guaranteed by the contract, not left to each deployment.
- Every storage adapter must pass tenant-isolation fixtures.
- Hosts must always supply a principal, including for batch jobs.

## Alternatives considered
- **Optional principal / anonymous sessions** — simpler for demos, unacceptable for audit.
- **Tenant isolation left to deployments** — too easy to get wrong.
