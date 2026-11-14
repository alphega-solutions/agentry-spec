# ADR-0007: Configuration merge rules are declared in the schema; loading is all-or-nothing

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `notes/config.md`; `notes/hooks.md` §5

## Context
Policy bundles, personas, profiles, and run requests all set overlapping values. Three implementations must combine them identically, and no lower layer may weaken governance.

## Decision
- Each schema field declares how it merges, via `x-agentry-merge`: `union`, `intersect`, `min`, `stricter` (with a declared strictness order), `locked`, or `override`.
- Precedence: policy bundle stack → persona → harness profile → run request. Environment overlays follow the same rules.
- A lower layer that tries to loosen a value is a **configuration error**, never a silent clamp.
- Loading proceeds discover → validate → resolve → merge → semantic validation → freeze. Any error means nothing loads.
- A run request may choose a profile only from the persona's `allowedProfiles`, and may only tighten values (`min`, `stricter`, `intersect` fields) (C2).
- The result is an immutable snapshot identified by a content hash; sessions are pinned to it, including across `resume`.
- If a pinned snapshot is unavailable, `resume` fails with an explicit error; it never silently falls back to the current configuration.

## Consequences
- Merge behaviour is data, so all implementations derive it from the same schemas.
- Authors get explicit errors when their settings are refused.
- Snapshots referenced by live or resumable sessions must be retained until those sessions end or expire.

## Alternatives considered
- **Merge logic in code per implementation** — would drift across languages.
- **Silent clamping to the stricter value** — hides misconfiguration from authors.

## Note 2026-11-14
The run-request rule above is narrowed by CFG-101 as amended 2026-11-14 (spec/02-configuration.md). A run request tightens only the `min` and `stricter` harness profile fields that CFG-101 lists, as run-scoped or session-scoped. It sets no `intersect` field (such as `model.fallbacks`) and does not set `guardrails.requireDeterministic`. The decision is otherwise unchanged.
