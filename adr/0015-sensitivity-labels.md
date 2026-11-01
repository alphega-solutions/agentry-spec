# ADR-0015: Extensible sensitivity labels with policy mapping

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `notes/tools.md` §2 (sensitivity labels); `notes/hooks.md` §3 (`annotate`)

## Context
Different deployments handle different kinds of sensitive data. Labels must be extensible without letting an unknown label slip through unhandled.

## Decision
- `sensitivity` is a set of labels. The spec defines well-known labels `pii`, `phi`, `pci`, `secret`; custom labels are namespaced (`<reverse-domain>:<label>`). Un-namespaced labels are reserved for the spec.
- Labels have no behaviour of their own. **Sensitivity policies** map labels to redaction, allowed providers, trace handling, and approval.
- A label with no policy mapping is a configuration error at load time (fail closed).
- When several labels apply, the strictest outcome of each behaviour wins.
- Labels propagate: tool results inherit their tool's labels, and hooks can add labels through `annotate`.

## Consequences
- Deployments can define domain-specific categories (e.g. clinical notes) safely.
- Every label in use must have a policy before configuration loads.

## Alternatives considered
- **A fixed enum** — simpler, but forces every deployment into the same categories.
