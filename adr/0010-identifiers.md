# ADR-0010: UUIDv7 identifiers; sequence numbers order events

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `notes/core.md` §4, K1

## Context
Sessions, runs, and events need identifiers that are unique across tenants and implementations, and events need a reliable order.

## Decision
- Session, run, and event IDs are **UUIDv7**.
- Within a session, a **sequence number** — strictly increasing and gap-free — is the only ordering authority for persisted events. Timestamps (RFC 3339 UTC) are informational.
- Ephemeral `model.delta` events carry no sequence number.

## Consequences
- IDs are time-sortable and supported by standard libraries in all three languages.
- Ordering does not depend on clocks.

## Alternatives considered
- **ULID** — similar properties, but not an IETF standard.
- **Timestamp ordering** — unreliable across processes and clock skew.
