# Area specifications

All areas approved 2026-10-31 (contract version 0.1.0-draft). Each spec lists its requirement IDs, conformance fixtures to write in Phase 4, and dated amendments from later areas at the end.

| Area | Spec | Prefix |
|---|---|---|
| 1 | [Core model](01-core.md) — sessions, runs, events, content, errors | `CORE-` |
| 2–3 | [Configuration, personas, harness profiles](02-configuration.md) | `CFG-` |
| 4 | [Tools](04-tools.md) | `TOOL-` |
| 5 | [Hooks, guardrails, taint rule](05-hooks.md) | `HOOK-` |
| 6 | [Human-in-the-loop](06-hitl.md) | `HITL-` |
| 7 | [Context and retrieval](07-context.md) | `CTX-` |
| 8 | [Orchestration (delegation)](08-orchestration.md) | `ORCH-` |
| 9 | [Providers](09-providers.md) | `PROV-` |
| 10 | [Storage ports](10-storage.md) | `PORT-` |
| 11 | [Conformance, testing, evaluation](11-evaluation.md) | `EVAL-` |

Amendments are recorded at the end of the spec they change. When reading an area, read its amendments too.

## How to read a spec

- **Requirements** are the bullets `- **AREA-NNN** …`. Only their bold key words (**MUST**, **MUST NOT**, **MAY** …, RFC 2119) are normative. A requirement marked *(untestable: …)* is verified another way, listed in `conformance/coverage.yaml`.
- **Amendments** are the dated `## Amendment YYYY-MM-DD` sections at the end of each area. They change the area in one of three ways:
  - **Edit the base text.** The amendment says "text above edited", and the edited requirement may carry an *(Amended …)* or *(Edited …)* marker.
  - **Replace a requirement.** The base requirement carries a *(Superseded …)* marker pointing to its replacement.
  - **Add a reading.** Readings are bullets such as `- HOOK-091: …` that settle how a requirement is read, typically when fixtures were written. They bind like the requirement they read.

  Older amendments (before 2026-11-07) did not always mark the base text. When base text and a later amendment disagree, the amendment wins.
- **Readings are kept current.** A reading inside an older amendment section may cite a later amendment, where that amendment refined it.
- **"Conformance fixtures (to be written in Phase 4)"** tables are the historical plan, kept for traceability. Today every fixture names the requirements it verifies in its own `requirements` list, and `tools/coverage.py` enforces that every normative requirement has one, apart from those listed as verified elsewhere or pending in `conformance/coverage.yaml`.
- **"Additions approved with this spec"** tables record what an area added beyond its design note when it was approved.

## Accepted decisions not yet specified

These ADRs are accepted but are not yet requirements. They target **1.x** and change nothing in 1.0.

| ADR | Decision | Areas it will amend |
|---|---|---|
| [ADR-0016](../adr/0016-memory-store.md) | Memory store port; memory references keep provenance and labels | 7, 10 (and 2 for `memoryStores`, `trustedMemoryStores`) |
| [ADR-0017](../adr/0017-skills.md) | `Skill` configuration artifacts, loaded on demand | 2, 7 |
| [ADR-0018](../adr/0018-reviewed-behaviour-changes.md) | Learned behaviour changes only through review | 6 |
| [ADR-0019](../adr/0019-shadow-mode.md) | Shadow mode for rolling out hooks and approval rules | 2, 5, 11 |
