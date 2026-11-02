# Area 10 — Storage ports

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `intent.md` G5; `domain.md` (approved, incl. amendments); ADR-0002, 0009, 0014, 0015; Areas 1–9 (approved)

---

## 1. Scope

Every external capability agentry depends on is reached through a **port**: a contract with swappable adapters (G5). This area specifies the rules all ports share and the contract of each: config source, event log, checkpoint store, idempotency store, snapshot store, blob store, audit log, vector store, secrets provider, and the optional telemetry exporter. It also covers write consistency, data residency, retention, and migration of stored data.

Earlier areas refer to a "trace sink". This area splits it in two: the **event log**, which holds the persisted, ordered events that make up the trace (CORE-160), and the optional **telemetry exporter** for observability spans (also the home of the spans mentioned in HOOK-061). This area is Tier 3 and has no design note.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `PORT-`. Operation names are illustrative; signatures are language-specific, but behaviour is normative.

## 3. Rules for all ports

- **PORT-001** Implementations **MUST** reach each capability in this area only through its port, so any conforming adapter can be substituted.
- **PORT-002** Every port that stores data **MUST** be tenant-scoped: every operation takes a tenant, and a record is visible only to its own tenant. Access to another tenant's record **MUST** behave exactly as if the record does not exist (`not_found`, CORE-193). This applies to: event log, checkpoint store, idempotency store, snapshot store, blob store, audit log, and vector store.
- **PORT-003** Ports **MUST NOT** share stored records across tenants, including by content-addressed deduplication; identical content stored by two tenants is two records.
- **PORT-004** Port errors **MUST** use the Area 1 error model: transient failures `unavailable` (`retryable: true`); version or lease mismatches `conflict`; missing records `not_found`.
- **PORT-005** Every storage binding, telemetry destination, and secrets provider in the deployment **MUST** declare its region. One whose region does not satisfy the effective `dataResidency` (CFG-070) is a configuration error.
- **PORT-006** Adapters for the event log, checkpoint store, idempotency store, snapshot store, blob store, audit log, and vector store **MUST** encrypt data at rest, using platform or customer-managed keys as the deployment configures.
- **PORT-007** Every stored record **MUST** carry `schemaVersion` (ADR-0002).
- **PORT-008** Ports return content as stored. Redaction for anything leaving the implementation — events streamed to hosts, reviewer views, telemetry — is applied by the implementation at that boundary, per the sensitivity policies in force.
- **PORT-009** Every adapter **MUST** pass the shared adapter test kit for its port (§15).

## 4. Config source

- **PORT-010** The config source lists and reads configuration artifacts (Areas 2–3). It is supplied to the loader at startup, outside configuration (CFG-110).
- **PORT-011** A config source **MUST** return a consistent set of artifacts for one load: an artifact changed during a load **MUST NOT** produce a mix of old and new versions.

## 5. Event log

- **PORT-020** The event log stores a session's persisted events. `append(tenant, session, events, expectedSeq, lease)` **MUST** succeed only if `expectedSeq` is the next sequence number in the log and `lease` is the session's current run lease; otherwise it fails with `conflict`. This enforces CORE-160 and lease fencing across processes.
- **PORT-021** `read(tenant, session, fromSeq, toSeq)` **MUST** return events in sequence order with no gaps.
- **PORT-022** Persisted events **MUST NOT** be modified, and are deleted only by retention, a whole session at a time (§13).

## 6. Checkpoint store

- **PORT-030** The checkpoint store holds each session's resumable state, including at least:
  - state, pinned principal reference, tenant, persona, snapshot hash;
  - taint state and tainting provenances (HOOK-126);
  - remaining turn budget and content-size counters (CFG-091, CORE-115, ORCH-041);
  - reasoning parts required for continuation (CORE-140);
  - the open escalation (HITL-012) with its full, unredacted pending content for reviewer views, recorded decisions, and partial multi-reviewer approvals (HITL-051);
  - results held while suspended (HITL-072, TOOL-033);
  - the run lease (HITL-090);
  - parent session ID and child session IDs for delegation chains (ORCH-004, ORCH-071).
- **PORT-031** `save(tenant, session, checkpoint, expectedVersion, lease)` **MUST** fail with `conflict` if the stored version differs or the lease is not current. This enforces one active run per session (CORE-032). Lease renewal is itself a versioned save.
- **PORT-032** The checkpoint store **MUST** support, per tenant:
  - `listPendingEscalations` — root escalations only, excluding chains whose earliest TTL has elapsed (HITL-100, ORCH-063, ORCH-065);
  - a query for sessions whose TTL has elapsed or whose lease has lapsed, for expiry (CORE-041) and recovery (HITL-091);
  - `children(session)` — the child sessions of a session (ORCH-070, ORCH-081).
- **PORT-033** No operation **MUST** return records of more than one tenant. Implementations that serve several tenants run these queries per tenant.

### 6.1 Consistency between events and checkpoints

- **PORT-034** The event log is authoritative for a session's sequence. When loading a session, an implementation **MUST** read any events beyond the checkpoint's last accounted sequence number and apply them to rebuild state before continuing. A crash between appending events and saving the checkpoint therefore loses nothing.
- **PORT-035** A checkpoint **MUST NOT** account for a sequence number that is not in the event log.

## 7. Idempotency store

- **PORT-040** `start(tenant, key, record, lease)` **MUST** create a started record only if none exists for the key and the lease is current; otherwise it returns the existing record, or fails with `conflict` if the lease is stale.
- **PORT-041** `complete(tenant, key, outcome, lease)` **MUST** record the outcome once; a second completion with a different outcome **MUST** fail with `conflict`.
- **PORT-042** Records **MUST** be kept at least until the session that created them closes (TOOL-061, ORCH-002), and then per retention (§13).

## 8. Snapshot store

- **PORT-050** The snapshot store holds effective configuration snapshots, keyed by tenant and snapshot hash (CFG-050). Price tables live in snapshots (PROV-074).
- **PORT-051** A snapshot **MUST** be retained while any session pinned to it is not closed (CFG-053), and while any retained audit record or event references its hash (§13). `get` of a missing snapshot returns `not_found`, which makes `resume()` fail (CORE-055).
- **PORT-052** Snapshots **MUST NOT** contain secret values (CFG-063).

## 9. Blob store

- **PORT-060** `put(tenant, bytes, mediaType, labels)` **MUST** return a blob reference: ID, content hash, media type, size (CORE-113).
- **PORT-061** `get(tenant, ref)` **MUST** verify the content hash and fail with `fatal` if it does not match.
- **PORT-062** Blobs **MUST** keep the sensitivity labels of the content they hold, so sensitivity policies apply to them as to any content.

## 10. Audit log

- **PORT-070** The audit log is append-only. Records **MUST NOT** be modified, and are deleted only by retention (§13).
- **PORT-071** Every audit record **MUST** include: timestamp, tenant, session ID, principal reference, snapshot hash, what happened (hook decision, policy decision, escalation, decision, mutating tool call), the reviewer for decisions (HITL-020, HITL-044), and the IDs linking it to events.
- **PORT-072** The audit log **MUST** support reading by tenant, filtered by session, time range, and record type, for auditors.
- **PORT-073** The audit log **SHOULD** be tamper-evident, for example by chaining record hashes. If it is, retention deletion **MUST** keep the hash of the last deleted record so the remaining chain still verifies.
- **PORT-074** Audit records **MUST NOT** contain secret values, and **MUST** apply the redaction of the sensitivity policies in force.

## 11. Vector store and secrets provider

### 11.1 Vector store

- **PORT-080** `query(tenant, principal, source, text, limit)` **MUST** return only content the principal may access in that tenant, filtering inside the port before results are returned (CTX-041).
- **PORT-081** Each result **MUST** carry its stored sensitivity labels, if any (CTX-042).
- **PORT-082** Ingesting content into a vector store is the host's responsibility and outside this contract.

### 11.2 Secrets provider

- **PORT-090** `resolve(tenant, reference, principal?)` returns a secret value, resolving per principal where the tool's credential mode is `principal` (CFG-062).
- **PORT-091** Implementations **MUST NOT** persist resolved values. Any cache **MUST** be keyed by tenant and principal, and **MUST NOT** outlive the call that needed the value unless the secrets provider declares a cache duration.

## 12. Telemetry exporter (optional)

- **PORT-100** An implementation **MAY** export observability spans. Exported spans **SHOULD** follow the OpenTelemetry semantic conventions for generative AI.
- **PORT-101** Exported spans **MUST** apply the same redaction as events streamed to hosts, and **MUST NOT** contain secret values, or reasoning parts unless the profile includes reasoning in traces (CORE-143).
- **PORT-102** Telemetry is never a system of record. Governance and replay depend only on the event log, blob store, snapshot store, and audit log (CTX-001).

## 13. Retention

- **PORT-110** The deployment **MUST** declare a retention period for: events, checkpoints of closed sessions, idempotency records, blobs, snapshots, and audit records. There are no spec defaults; regulated deployments set the periods their regime requires.
- **PORT-111** Retention **MUST NOT** delete data of a session that is not closed, whatever the period.
- **PORT-112** Dependent data **MUST** outlive what references it: blobs and snapshots at least as long as the events and audit records that reference them; audit records at least as long as the events they describe.
- **PORT-113** Events **MUST** be deleted a whole session at a time, never leaving gaps (PORT-021).
- **PORT-114** A deployment **MAY** place a **legal hold** on a tenant or session. While a hold applies, no retention deletion occurs for the held data.
- **PORT-115** Once a closed session's checkpoint is deleted by retention, a replayed `resume()` for it returns `not_found` rather than the original outcome (CORE-053 applies only while the checkpoint is retained). Decisions remain in the audit log.

## 14. Migration between contract versions

- **PORT-120** Within a major version, implementations **MUST** read records written by any earlier minor version.
- **PORT-121** A new major version **MUST** ship a migration for checkpoints of sessions that are not closed. Events and audit records are never rewritten; readers for the old major version **MUST** remain available for them.
- **PORT-122** A session **MUST NOT** be resumed by an implementation whose contract major version differs from the session's checkpoint, unless the checkpoint has been migrated.

## 15. Adapter test kit

- **PORT-130** For each port, the spec repository provides contract fixtures that every adapter, in every language, must pass, covering at least: tenant isolation and `not_found` across tenants, no cross-tenant deduplication, version and lease conflicts, ordering, idempotent creation, retention protection, legal holds, and `schemaVersion` on every record.

## 16. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Swap adapters → identical conformance results | PORT-001, 009 |
| Other tenant's record → `not_found` on every port, including snapshots | PORT-002 |
| Identical content in two tenants → two records; no existence leak | PORT-003 |
| Port errors mapped | PORT-004 |
| Storage, telemetry, or secrets region outside `dataResidency` → rejected | PORT-005 |
| Adapter reports encryption at rest configured | PORT-006 |
| Every record has `schemaVersion` | PORT-007 |
| Host-facing outputs redacted; internal reads full | PORT-008 |
| Config source change mid-load → consistent set | PORT-011 |
| Event append: wrong `expectedSeq` or stale lease → `conflict`; gap-free reads; events immutable | PORT-020–022 |
| Checkpoint contents round-trip | PORT-030 |
| Stale version or lease → `conflict` | PORT-031 |
| Pending (root only, unexpired), expiry/recovery, and children queries, per tenant | PORT-032, 033 |
| Crash after append, before checkpoint → state rebuilt from events | PORT-034 |
| Checkpoint never ahead of event log | PORT-035 |
| Idempotency: start returns existing; stale lease → `conflict`; conflicting completion → `conflict`; kept until close | PORT-040–042 |
| Snapshot kept while sessions open or referenced; missing → `not_found`; no secrets | PORT-050–052 |
| Blob hash verified; mismatch → `fatal`; labels kept | PORT-060–062 |
| Audit append-only; contents incl. reviewer; queryable by tenant; chain verifies after retention; no secrets | PORT-070–074 |
| Vector query filtered by tenant and principal; labels returned | PORT-080, 081 |
| Secrets not persisted; cache keyed by tenant and principal | PORT-090, 091 |
| Telemetry redacted; replay works with telemetry disabled | PORT-101, 102 |
| Retention: open sessions untouched; dependencies outlive referrers; whole-session event deletion | PORT-111–113 |
| Legal hold blocks deletion | PORT-114 |
| Replayed resume after checkpoint retention → `not_found` | PORT-115 |
| Older minor records readable; resume across major refused without migration | PORT-120, 122 |

## 17. Additions approved with this spec (2026-10-31)

All rules here are new; this is a Tier 3 area.

| ID | Proposed rule |
|---|---|
| §1 | **"Trace sink" split into the event log (system of record) and an optional telemetry exporter** (amends `domain.md` §9 port list) |
| PORT-001, 009 | Capabilities only through ports; every adapter passes the test kit |
| PORT-002, 003 | **All storing ports tenant-scoped, including the snapshot store; no cross-tenant deduplication** |
| PORT-004 | Port errors use the Area 1 model |
| PORT-005 | Region declared for storage, telemetry, and secrets, checked against `dataResidency` |
| PORT-006 | **Encryption at rest required** for every storing port |
| PORT-007, 008 | `schemaVersion` on every record; redaction applied at the boundary, not in storage |
| PORT-010, 011 | Config source supplied at startup; consistent loads |
| PORT-020–022 | Event log append with expected sequence and lease; whole-session deletion only |
| PORT-030–033 | Checkpoint contents; versioned, lease-fenced saves; per-tenant queries for pending escalations, expiry/recovery, and children |
| PORT-034, 035 | **Event log authoritative; state rebuilt from events after a crash** |
| PORT-040–042 | Lease-fenced idempotency store |
| PORT-050–052 | Snapshot store; snapshots kept while referenced by retained events or audit records |
| PORT-060–062 | Blob hash verification; labels kept |
| PORT-070–074 | Audit log append-only, queryable, with reviewer; **tamper-evidence recommended (SHOULD)** with chain-preserving deletion |
| PORT-080–082 | Vector store query contract; ingestion out of scope |
| PORT-090, 091 | Secrets resolved per tenant and principal; never persisted |
| PORT-100–102 | Optional telemetry following OpenTelemetry GenAI conventions; never a system of record |
| PORT-110–115 | **Retention periods required, no defaults**; dependency ordering; whole-session deletion; **legal holds**; replayed resume after retention returns `not_found` |
| PORT-120–122 | Migration rules across contract versions |
| PORT-130 | Shared adapter test kit contents |

## Amendment 2026-11-01 — from Phase 4 review

- PORT-030: the checkpoint holds **all** reasoning parts (CORE-140), not only those required for continuation.


## Amendment 2026-11-01 — from Phase 4 (Area 7 fixtures)

- PORT-080: `principal` is the principal's subject, tenant and roles, so a port can filter by role as well as by subject.

## Amendment 2026-11-02 — from Phase 4 (schemas and fixtures)

Schemas: stored records in `schemas/ports/v1/records.yaml` (checkpoint, idempotency record, snapshot, blob metadata, audit record, lease); the port test-kit case format in `conformance/schema/port-case.yaml`.

**Two kinds of fixture**

- The adapter test kit (PORT-009, PORT-130) is a set of **port cases** in `conformance/ports/`. Each calls one port's operations directly, with language-neutral names and arguments listed in the format; every adapter of that port, in every language, must pass every case for it. In-memory adapters used by the conformance suite pass them too (EVAL-033).
- Harness-level storage behaviour (retention, legal holds, consistency between events and checkpoints, residency, redaction at the boundary) is verified by ordinary fixtures in `conformance/storage/`. A `retention: {}` step runs retention processing at the current virtual time.
- PORT-001, PORT-009: substitutability is verified by running the whole suite with each conforming adapter; results must be identical.

**Records and leases**

- PORT-030: the checkpoint record is the `checkpoint` schema; `version` increases by one on every save, including lease renewals, and `lastSeq` is the last event sequence number it accounts for.
- PORT-020, PORT-031, PORT-040: a lease carries a **fencing token**, strictly greater for each new lease of a session and unchanged by renewal. Every port that takes a lease rejects with `conflict` a write whose token is lower than the highest it has accepted for that session. This is how the event log and idempotency store recognise a stale lease without consulting the checkpoint store.
- PORT-071, PORT-073: the audit record is the `auditRecord` schema, with `details` per type as earlier areas define them; a tamper-evident log chains `hash` and `prevHash` (SHA-256 of the RFC 8785 canonical record without `hash`), and keeps the hash of the last deleted record as the next record's `prevHash` after retention.
- PORT-006: every storing port reports through `describe` whether encryption at rest is configured.
