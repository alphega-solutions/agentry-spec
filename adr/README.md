# Architecture Decision Records

Phase 2 records every cross-cutting decision made during Phases 0–1. ADR-0001–0015 were accepted on 2026-10-31, when Phase 2 was approved; ADR-0016–0020 were accepted on 2026-11-14, after the post-Phase 4 review. An accepted decision is changed only by a new ADR that supersedes it. A dated **Note** may record how later specs refine an ADR's details without changing its decision (see ADR-0007, ADR-0008, ADR-0015).


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
| [0019](0019-shadow-mode.md) | Shadow mode for rolling out hooks and approval rules | Accepted |
| [0020](0020-shared-conformance-runner.md) | One shared conformance runner; implementations provide a driver | Accepted |

## Pending

- Further ADRs will be added as Tier 2 notes settle (HITL, context and memory, providers, content).
- ADR-0016–0019 (memory, skills, reviewed behaviour changes, shadow mode), accepted 2026-11-14, target **1.x** and change nothing in 1.0. They enter the spec as amendments with schemas and fixtures: ADR-0016–0018 in Areas 2, 6, 7 and 10, and ADR-0019 in Areas 2, 5 and 11. `spec/README.md` lists them under "Accepted decisions not yet specified".
- ADR-0020 (shared runner) is applied: EVAL-020 as amended 2026-11-14, `conformance/schema/driver.yaml` and `tools/runner/`.
