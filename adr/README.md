# Architecture Decision Records

Phase 2 records every cross-cutting decision made during Phases 0–1. All ADRs below were accepted on 2026-10-31 when Phase 2 was approved. Accepted ADRs are changed only by a new ADR that supersedes them.


| ADR | Decision | Status |
|---|---|---|
| [0001](0001-json-schema.md) | JSON Schema 2020-12 is the normative schema format | Accepted |
| [0002](0002-versioning.md) | Contract versioning and compatibility | Accepted |
| [0003](0003-loop-ownership.md) | The harness owns the agent loop | Accepted |
| [0004](0004-session-durability.md) | The session is the unit of durability; agentry is not a workflow engine | Accepted |
| [0005](0005-streaming.md) | Streaming: step events are core, token deltas optional, buffered by default | Accepted |
| [0006](0006-cel-rules.md) | CEL subset as the declarative rule language | Accepted |
| [0007](0007-config-merge.md) | Configuration merge rules are declared in the schema; loading is all-or-nothing | Accepted |
| [0008](0008-provenance-taint.md) | Provenance, taint, and egress control | Accepted |
| [0009](0009-error-model.md) | One error model across all components | Accepted |
| [0010](0010-identifiers.md) | UUIDv7 identifiers; sequence numbers order events | Accepted |
| [0011](0011-license.md) | Public spec under Apache-2.0 with DCO; private implementations | Accepted |
| [0012](0012-naming.md) | Package naming under the alphega namespace | Accepted |
| [0013](0013-langchain.md) | LangChain is an optional integration, never a core dependency | Accepted |
| [0014](0014-identity-tenancy.md) | Principal identity and tenant isolation | Accepted |
| [0015](0015-sensitivity-labels.md) | Extensible sensitivity labels with policy mapping | Accepted |
| [0016](0016-memory-store.md) | Memory as a port with references that keep provenance and labels | Accepted |
| [0017](0017-skills.md) | Skills are configuration artifacts, loaded on demand by the model | Accepted |
| [0018](0018-reviewed-behaviour-changes.md) | Learned behaviour changes only through review | Accepted |
| [0019](0019-shadow-mode.md) | Shadow mode for rolling out hooks and approval rules | Proposed |

## Pending

- [ ] Inventory ADRs from the earlier `@alphega/agentry` scaffold and mark each keep / revise / retire (needs repo access).
- Further ADRs will be added as Tier 2 notes settle (HITL, context and memory, providers, content).
- ADR-0016–0018 (memory, skills, reviewed behaviour changes), accepted 2026-11-14, govern a 1.x extension and change nothing in 1.0; they enter the spec as Areas 2, 6, 7 and 10 amendments with schemas and fixtures.
