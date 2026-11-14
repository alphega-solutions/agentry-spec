# ADR-0008: Provenance, taint, and egress control

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `notes/security.md`

## Context
Models cannot reliably separate instructions from data. Tool results and retrieved documents can carry injected instructions that steer an agent to change records or send sensitive data out.

## Decision
- All content carries **provenance**. Tool results, retrieval, and anything derived from them are **untrusted** unless a policy bundle explicitly marks a tool `trustedOutput: true`.
- A turn becomes **tainted** when untrusted content enters its context; taint is sticky for the rest of the session in 1.0.
- The **taint rule**, evaluated deterministically before hooks:
  - Tainted turn → mutating tool: escalate by default (`onTainted` may set `block` or `allow`).
  - Tainted turn → egress tool with sensitive-labelled content in context: block by default (`onTainted` may set `escalate`; never `allow`).
  - Lower configuration layers cannot loosen these defaults.
  - A tool's minimum assurance level is checked together with the taint rule, before hooks.
- Tool definitions gain `egress`, `onTainted`, `credentialMode`, and an optional minimum assurance level.
- Provider adapters must delimit untrusted content in prompts, as defence in depth only.

## Consequences
- The main injection and exfiltration paths are closed by policy, not by model behaviour.
- Some legitimate flows will require approval until policies are tuned.
- Provenance is recorded in traces, so audits show what influenced each action.

## Alternatives considered
- **Relying on prompt formatting and model instructions** — not a security boundary.
- **Clearing taint on compaction** — more permissive, but harder to reason about and audit.

## Note 2026-11-14
Later specs refine this decision; the decision itself stands:
- **Trust** is granted by listing a tool in a policy bundle's `trustedTools` (CFG-070, CFG-071). A tool definition may not declare `trustedOutput` (TOOL-004).
- **Egress** uses its own outcome field, `onTaintedEgress` (`block` or `escalate`, never `allow`), separate from `onTainted` (TOOL-001).
- **The egress condition** is that any sensitivity label has entered the session (its label set, HOOK-127, 2026-11-13), not that labelled content is in context now. Compaction can drop labelled content, but it cannot clear the label set.