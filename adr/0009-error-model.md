# ADR-0009: One error model across all components

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `notes/core.md` §7; `notes/security.md` §6 (tenant isolation)

## Context
Tools, hooks, providers, storage ports, and the harness all fail in different ways. The loop, callers, and three implementations need one consistent way to decide what happens next.

## Decision
- One error shape: `code` (namespaced, stable), `category`, `retryable`, `source`, safe `message`, and `details`.
- Categories: `invalid_input`, `unauthorized`, `policy`, `limit`, `unavailable`, `conflict`, `not_found`, `configuration`, `cancelled`, `fatal`. Behaviour is driven by category, never by parsing messages.
- Messages never contain sensitive content; `details` follow the same sensitivity labels and redaction as any content.
- Wrong-tenant access returns `not_found`, never a distinct "forbidden".

## Consequences
- Retry, escalation, and run-end behaviour is uniform across implementations and providers.
- Vendor-specific errors are mapped into this model by adapters; original vendor detail goes in `details`, subject to redaction.

## Alternatives considered
- **Per-component error types** — simpler locally, inconsistent globally.
