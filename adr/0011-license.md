# ADR-0011: Public spec under Apache-2.0 with DCO; private implementations

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` Q2, Q8, and §7 Constraints

## Context
Public review and scrutiny strengthen a governance-first spec. The reference implementations are commercial assets and remain private for now.

## Decision
- This repository is public under **Apache-2.0** (its explicit patent grant suits schemas, fixtures, and codegen).
- Outside contributions require **Developer Certificate of Origin** sign-off.
- Reference implementations are private for now.
- Nothing in this repository may depend on, describe, or leak private code, client details, or the internals of any consuming product. The conformance suite must be runnable by anyone.

## Consequences
- Third parties can build conforming implementations from this repository alone.
- **Added in this ADR (approved 2026-10-31):** every change is reviewed for leakage of private details before merge (enforced through CODEOWNERS).

## Alternatives considered
- **CC-BY-4.0 for prose** — fine for text, but lacks a patent grant for schemas and code.
- **A contributor license agreement** — heavier for contributors than DCO.
