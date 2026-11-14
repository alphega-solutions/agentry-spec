# Areas 2–3 — Configuration, personas, and harness profiles

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `domain.md` (approved, incl. amendments); notes `config.md`, `hooks.md`, `tools.md`, `security.md`, `content.md` (settled); ADR-0001, 0002, 0005, 0006, 0007, 0008, 0014, 0015; Area 1 (approved)

---

## 1. Scope

This document specifies the configuration model shared by all areas (artifacts, references, layering, loading, snapshots, secrets), and the contents of three artifact kinds: **policy bundles**, **personas** (Area 2), and **harness profiles** (Area 3). It also fixes the **deployment** artifact's boundary.

The contents of `Tool` and `Hook` artifacts are specified in Areas 4 and 5. Fields marked *(Area n)* are declared here so layering applies to them, but their semantics belong to that area.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `CFG-`.

## 3. Artifacts

- **CFG-001** Every configuration artifact **MUST** be a single document with: `kind`, `id`, `version`, and `schemaVersion`.
- **CFG-002** `kind` **MUST** be one of `PolicyBundle`, `Persona`, `HarnessProfile`, `Tool`, `Hook`, `Deployment`.
- **CFG-003** The pair (`id`, `version`) **MUST** be unique within its kind in a snapshot; several versions of one artifact may coexist. `version` **MUST** be a positive integer (ADR-0002).
- **CFG-004** The canonical form is one artifact per file, in YAML or JSON. A bundle of artifacts is a directory or archive of such files.
- **CFG-005** Every artifact **MUST** validate against its kind's JSON Schema (ADR-0001) before any further processing.

## 4. References

- **CFG-010** Artifacts reference one another as `id@version`. Version ranges and unversioned references **MUST** be rejected.
- **CFG-011** Every reference **MUST** resolve to an artifact of the expected kind in the same snapshot. An unresolved reference is a configuration error.
- **CFG-012** Reference cycles (for example, two personas that can delegate to each other) are permitted. Limits on delegation depth are specified in Area 8.

## 5. Layering and merge rules

### 5.1 Layers

Behavioural values are merged across layers, highest first:

1. Policy bundle stack, in declared order (e.g. organisation, then department)
2. Persona
3. Harness profile
4. Run request
5. Environment overlay (tighten only)

- **CFG-020** Each layer **MUST** be merged onto the result of the layers above it using the merge rule of each field.
- **CFG-021** Deployment artifacts **MUST NOT** set behavioural values. Environment overlays **MAY** set deployment fields freely and **MAY** tighten behavioural values under the same merge rules; they are applied last and **MUST NOT** loosen anything.

### 5.2 Merge rules

- **CFG-030** Every field of a behavioural artifact's schema **MUST** declare a merge rule via the `x-agentry-merge` annotation (ADR-0007):

| Rule | A lower layer may… |
|---|---|
| `union` | Add items |
| `intersect` | Remove items (narrow) |
| `min` | Lower the value |
| `stricter` | Move toward the stricter end of the field's declared strictness order |
| `locked` | Not change a value once a higher layer has set it |
| `override` | Replace the value (permitted only on non-governance fields) |

Absence and emptiness differ. For `intersect` fields, a layer that does not set the field imposes no constraint; an empty list means "nothing". For grant fields (`trustedTools`, `trustedAttachmentSources`), the effective value is the intersection of every layer that sets the field, and is empty if no layer sets it.

Map-valued fields merge per key: a lower layer **MAY** add new keys; for an existing key, each value merges by its own rule. For `sensitivityPolicies`, allowed providers `intersect`, approval is `stricter`, and redaction rules `union`. For `toolTaintDefaults`, each tool's outcome is `stricter`.

- **CFG-031** A field with merge rule `stricter` **MUST** declare its strictness order in the schema. Orders defined by the spec:

| Field family | Strictness order (strictest first) |
|---|---|
| Hook failure mode | `failClosed` → `failOpen` |
| Delivery mode | `buffered` → `streamed` |
| Taint outcome | `block` → `escalate` → `allow` |
| Approval policy | `always` → `policy` → `never` |
| Approval default (HOOK-133) | `escalate` → `continue` |
| Checkpoint granularity | `tool` → `turn` |
| Include reasoning in traces | `false` → `true` |

- **CFG-032** A lower layer that sets a value its merge rule does not permit **MUST** cause a configuration error naming the artifact, field, and layer. Implementations **MUST NOT** silently clamp the value.
- **CFG-033** `override` **MUST NOT** be used on any field that affects tools, hooks, providers, sensitivity, trust, limits, budgets, delivery, or retention. The provisional `model` and `context` fields (CFG-092) are the only exceptions, and remain subject to `allowedProviders` (CFG-042). *(untestable: a property of the spec's own schemas, enforced by spec CI rather than by implementation fixtures.)*
- **CFG-034** A hook referenced by a higher layer **MUST NOT** be replaced, re-versioned, or removed by a lower layer. A lower layer requiring a different version of a hook `id` already required above is a configuration error. This keeps a hook's failure mode and declared results intact (`notes/hooks.md` §5).

## 6. Loading

- **CFG-040** Implementations **MUST** load configuration in this order: discover → parse and schema-validate → resolve references → merge layers → semantic validation → freeze.
- **CFG-041** If any step fails for any artifact, **nothing** **MUST** be loaded. Implementations **MUST NOT** run with partial configuration.
- **CFG-042** Semantic validation **MUST** include at least:
  - layering violations (CFG-032)
  - a `streamed` delivery mode with any output hook that declares `block` (ADR-0005)
  - a `streamed` delivery mode with an output schema (Area 1, CORE-131)
  - a sensitivity label with no sensitivity policy (ADR-0015)
  - a declarative rule that uses CEL outside the agentry subset, or fails to compile or type-check (ADR-0006)
  - a selected model whose provider is not in the effective `allowedProviders`
  - an effective taint outcome of `allow` for an egress tool (ADR-0008); the effective outcome for a tool is the stricter of its own `onTainted` and any `toolTaintDefaults` entry
  - `trustedOutput` or trusted attachment sources set outside a policy bundle (ADR-0008)
  - a hook at `onError` or `sessionEnd` declaring `rewrite`, `block`, or `escalate` (Area 1, CORE-182)
- **CFG-043** Configuration is read through the **config source** port. A file-system source is the default; other sources (object storage, database) **MAY** be provided as adapters.

## 7. Snapshots

- **CFG-050** Successful loading **MUST** produce an immutable **effective configuration snapshot** identified by a **snapshot hash** computed over its normalized content.
- **CFG-051** Two loads of identical configuration **MUST** produce the same snapshot hash.
- **CFG-052** A new snapshot **MUST** apply only to sessions created after it is loaded. Existing sessions remain pinned to their snapshot (Area 1, CORE-012).
- **CFG-053** A snapshot referenced by any session that is not `closed` **MUST** remain retrievable, through a storage port specified in Area 10, until that session closes. If it cannot be retrieved, `resume()` fails per Area 1, CORE-055.
- **CFG-055** Signed or hash-pinned configuration is **OPTIONAL** in 1.0. The snapshot hash makes tampering detectable after the fact.
- **CFG-054** Every event and audit record **MUST** carry the snapshot hash (Area 1, CORE-150).

## 8. Secrets

- **CFG-060** Configuration **MUST NOT** contain secret values. Fields that take secrets **MUST** take a **secret reference** of the form `secret://<provider>/<name>`.
- **CFG-061** Schemas mark secret fields with the annotation `x-agentry-secret: true`. A secret field containing anything other than a secret reference **MUST** cause a configuration error.
- **CFG-062** Secret references are resolved at bind time through the secrets-provider port, keyed by principal where the tool's credential mode is `principal` (ADR-0014).
- **CFG-063** Resolved secret values **MUST NOT** appear in snapshots, events, traces, audit records, or error messages.

## 9. Policy bundles

A policy bundle holds mandatory organisational rules. Bundles may be stacked; each lower bundle can only tighten the ones above it.

- **CFG-070** A policy bundle **MAY** declare the following fields:

| Field | Merge rule | Meaning |
|---|---|---|
| `instructions` | `union` | Policy instructions added to every persona's system content; provenance `system` (Area 1, CORE-119) |
| `requiredHooks` | `union` | Hook references that every session must run *(Area 5)* |
| `sensitivityPolicies` | `union` | Label → behaviour mappings: redaction, allowed providers, trace handling, approval (ADR-0015) |
| `trustedTools` | `intersect` | Tools whose output is trusted (`trustedOutput`) (ADR-0008) |
| `trustedAttachmentSources` | `intersect` | Attachment sources treated as trusted (Area 1, CORE-121) |
| `allowedProviders` | `intersect` | Providers any persona may use *(Area 9)* |
| `toolTaintDefaults` | `stricter` | Per-tool overrides of the taint outcome *(Area 5)* |
| `approvalDefault` | `stricter` | Outcome of an `approval: policy` call when no approval rule is true; bundle-only (HOOK-133, Area 5 amendment 2026-11-13) |
| `defaultFallbackMessage` | `locked` | Fallback message when a persona declares none (Area 1, CORE-181) |
| `dataResidency` | `locked` | Region constraints for storage ports *(Area 10)* |

- **CFG-071** `trustedTools` and `trustedAttachmentSources` **MUST** be settable only in policy bundles. The same fields in any other kind are a configuration error.
- **CFG-072** A deployment **MUST** declare its policy bundle stack, which **MAY** be empty. With an empty stack, no tool output or attachment is trusted and no provider restriction applies beyond the persona's.

## 10. Personas (Area 2)

A persona declares **who** an agent is.

- **CFG-080** A persona **MUST** declare `instructions`, `tools`, `defaultProfile`, and `allowedProfiles`, and **MAY** declare the other fields below:

| Field | Merge rule | Meaning |
|---|---|---|
| `displayName`, `description` | `override` | Human-readable labels |
| `instructions` | `locked` | System content for the model; provenance `system` (Area 1, CORE-119) |
| `tools` | `intersect` | Tool allowlist, as `id@version` references *(Area 4)* |
| `requiredHooks` | `union` | Hooks this persona always runs *(Area 5)* |
| `fallbackMessage` | `locked` | Response when a run ends `blocked` |
| `outputSchema` | `locked` | Output schema for the final response (Area 1, §8.1) |
| `defaultProfile` | `locked` | Profile used when a run request names none |
| `allowedProfiles` | `intersect` | Profiles a run request may choose |
| `allowedProviders` | `intersect` | Providers this persona may use *(Area 9)* |

- **CFG-081** `defaultProfile` **MUST** be a member of `allowedProfiles`.
- **CFG-082** A persona's `tools` list **MUST** contain only references to `Tool` artifacts present in the snapshot. The model sees only the intersection of the tool catalog, this list, and the runtime scope *(Area 4)*.
- **CFG-083** Instructions **MUST NOT** contain secret references or secret values.

## 11. Harness profiles (Area 3)

A harness profile declares **how** a persona runs.

- **CFG-090** A harness profile **MUST** declare `idleTtl`, `suspendedTtl`, and `stepLimit`, and **MAY** declare the other fields below. `deliveryMode` defaults to `buffered` (ADR-0005).

| Field | Merge rule | Meaning |
|---|---|---|
| `idleTtl`, `suspendedTtl` | `min` | Session expiry (Area 1, §4.4) |
| `stepLimit` | `min` | Maximum steps per turn (Area 1, CORE-083) |
| `budget.tokens`, `budget.cost` | `min` | Token and cost budget per turn |
| `timeouts.run` | `min` | Wall-clock limit per run |
| `timeouts.tool` | `min` | Default tool timeout when a tool declares none *(Area 4)* |
| `retry.unavailable` | `min` | Maximum retries for `unavailable` errors (Area 1, CORE-191) |
| `outputRetryLimit` | `min` | Corrections allowed for an output schema (Area 1, CORE-132) |
| `outputSchema` | `locked` | Output schema, if the persona declares none |
| `deliveryMode` | `stricter` | `buffered` (default) or `streamed` (ADR-0005) |
| `checkpoint` | `stricter` | Checkpoint granularity: `tool` → `turn` (strictest first) |
| `limits.partSize`, `limits.sessionSize` | `min` | Content size limits (Area 1, CORE-115) |
| `defaultAttachmentLabels` | `union` | Labels applied to unscanned attachments (Area 1, CORE-123) |
| `trace.includeReasoning` | `stricter` | `false` → `true` (strictest first) (Area 1, CORE-143) |
| `requiredHooks` | `union` | Hooks this profile adds *(Area 5)* |
| `context` | `override` | Context strategy reference *(Area 7, provisional)* |
| `model` | `override` | Model selection *(Area 9, provisional)* |

- **CFG-091** Budgets apply per turn, so a `resume()` continues the suspended turn's budget rather than resetting it. When a budget is reached the run **MUST** end with `budget_exhausted` (Area 1, §5.2).
- **CFG-092** `context` and `model` are `override` only until Areas 7 and 9 define them. Those areas **MAY** change their merge rules.

## 12. Run requests

- **CFG-100** A run request **MAY** name a profile. It **MUST** be a member of the persona's `allowedProfiles`; otherwise the request fails with error category `invalid_input`. If none is named, `defaultProfile` applies.
- **CFG-101** A run request **MAY** set harness profile fields whose merge rule is `min` or `stricter`, and only to tighten them. Any other value **MUST** fail with error category `invalid_input`.
- **CFG-102** Run-request values for run-scoped fields apply to that run only and **MUST** be recorded on its `run.started` event. Values for session-scoped fields (CFG-101), which only the session-creating run request may set, apply to the session and **MUST** be recorded on `session.created`, not on `run.started`.

## 13. Deployment

- **CFG-110** A deployment artifact declares provider endpoints, storage port bindings, the secrets provider, the policy bundle stack, and the environment name. The config source itself is supplied to the loader at startup, outside configuration.
- **CFG-111** A deployment **MUST NOT** declare persona, profile, tool, or hook behaviour.
- **CFG-112** Environment overlays (`dev`, `staging`, `prod`) apply to deployment fields and **MAY** tighten behavioural values under CFG-021.

## 14. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Artifact missing `kind`/`id`/`version`/`schemaVersion` → rejected | CFG-001, 005 |
| Duplicate (`id`, `version`) within a kind → rejected; two versions of one id → accepted | CFG-003 |
| Unknown `kind` → rejected | CFG-002 |
| Unversioned or ranged reference → rejected | CFG-010 |
| Unresolved reference; wrong-kind reference → rejected; delegation cycle → accepted | CFG-011, 012 |
| Each merge rule applied correctly, including absent vs empty and per-key map merges | CFG-020, 030 |
| Each strictness order: tighten accepted, loosen rejected | CFG-031 |
| Lower layer re-versions a required hook → rejected | CFG-034 |
| Effective `allow` on an egress tool → rejected; stricter of tool and bundle applied | CFG-042 |
| Model from a disallowed provider → rejected | CFG-042 |
| Persona loosens a policy-bundle value → error names artifact, field, layer | CFG-032 |
| Department bundle loosens organisation bundle → rejected | CFG-020, 032 |

| One invalid artifact among many → nothing loads | CFG-041 |
| Each semantic validation in CFG-042 → rejected | CFG-042 |
| Identical configuration → identical snapshot hash | CFG-050, 051 |
| New snapshot does not affect existing sessions; resumed session keeps its original snapshot | CFG-052 |
| Missing pinned snapshot → `resume()` fails `not_found` | CFG-053 |
| Snapshot hash on every event and audit record | CFG-054 |
| Snapshot retained while a session is open | CFG-053 |
| Literal secret in a secret field → rejected; resolved value absent from events and errors | CFG-060, 061, 063 |
| Secret resolved per principal for `credentialMode: principal` | CFG-062 |
| Secret reference in persona instructions → rejected | CFG-083 |
| `trustedTools` in a persona → rejected | CFG-071 |
| Empty policy stack → no trusted tools or attachments | CFG-072 |
| `defaultProfile` not in `allowedProfiles` → rejected | CFG-081 |
| Persona tool reference to missing tool → rejected | CFG-082 |
| Profile missing a required field → rejected | CFG-090 |
| Budget reached → `budget_exhausted`; budget not reset by `resume()` | CFG-091 |
| Profile without `deliveryMode` → `buffered` | CFG-090 |
| Run request picks disallowed profile → `invalid_input` | CFG-100 |
| Run request tightens a budget → applied and recorded; loosens → `invalid_input` | CFG-101, 102 |
| Deployment declares persona behaviour → rejected | CFG-111 |
| Environment overlay tightens → applied; loosens → rejected | CFG-021, 112 |

Spec-maintenance check (not an implementation fixture): CI verifies that no governance field in the spec's schemas uses `override` (CFG-033).

## 15. Additions approved with this spec (2026-10-31)

These went beyond the settled notes and ADRs and were approved with this spec.

| ID | Proposed rule |
|---|---|
| CFG-004 | JSON is accepted alongside YAML |
| CFG-011 | A reference to an artifact of the wrong kind is an error |
| CFG-012 | Reference cycles are allowed; delegation depth limits move to Area 8 |
| CFG-030 | Absent vs empty semantics; grant fields; per-key merging of map fields |
| CFG-031 | Strictness orders for approval policy, checkpoint granularity, reasoning in traces |
| CFG-032 | Errors name the artifact, field, and layer |
| CFG-033 | The list of governance fields; `model`/`context` exempt while provisional |
| CFG-034 | A lower layer cannot re-version a hook required above |
| CFG-042 | Model must come from an allowed provider; effective taint outcome is the stricter of tool and bundle |
| CFG-050/051 | Snapshot hash over normalized content; identical input gives identical hash (normalization defined in Phase 4) |
| CFG-053 | Snapshots retained through a storage port (Area 10) |
| CFG-061 | Secret fields marked `x-agentry-secret` |
| CFG-063 | Secrets also excluded from error messages |
| CFG-070 | Policy bundle fields `instructions`, `defaultFallbackMessage`, `dataResidency`, and all merge-rule choices |
| CFG-072 | Deployment declares the policy stack; an empty stack is allowed |
| CFG-080/081 | Required persona fields; `defaultProfile` must be in `allowedProfiles` |
| CFG-083 | No secrets in persona instructions |
| CFG-090 | Profile fields `timeouts.run`, `timeouts.tool`, `retry.unavailable`, `checkpoint`, and all merge-rule choices |
| CFG-091 | **Budgets apply per turn**, so `resume()` does not reset them |
| CFG-100/101 | These failures use `invalid_input`; run requests may tighten only `min`/`stricter` profile fields |
| CFG-102 | Run-scoped run-request values recorded on `run.started`; session-scoped ones on `session.created` (as amended 2026-11-14) |
| CFG-110 | Config source supplied at startup, outside configuration |

## Amendment 2026-10-31 — from Area 4

- CFG-110: a deployment also declares MCP servers by endpoint and identity (TOOL-093).
- CFG-042: effective taint outcomes now cover two tool fields, `onTainted` (mutating) and `onTaintedEgress` (egress); `toolTaintDefaults` entries apply to each (TOOL-001, TOOL-003).

## Amendment 2026-10-31 — from Area 5

- CFG-042: a `streamed` profile is also invalid if any `afterModelCall` or `beforeResponse` hook declares `rewrite`, `block`, or `escalate`, or is `failClosed` (HOOK-040 as amended 2026-11-07).
- CFG-070, CFG-080: policy bundles and personas may declare `approvalRules` (merge `union`) (HOOK-130).
- CFG-070, CFG-090: policy bundles and profiles may set `guardrails.requireDeterministic` (merge `stricter`, order `true` → `false`) (HOOK-104).
- CFG-110: a deployment also declares remote hook endpoints (HOOK-092).

## Amendment 2026-10-31 — from Area 6

- CFG-070, CFG-080: policy bundles and personas may declare `reviewerRules` per escalation source (merge `union`), each optionally with `requiredApprovals` (HITL-021, HITL-024).
- CFG-070: policy bundles may set `allowSelfApproval` per escalation source (merge `stricter`, order `false` → `true`); never effective for `taint` or `recovery` (HITL-023). Sensitivity policies gain an optional `reviewerRule` (merge `union`) (HITL-031).
- CFG-090: harness profiles may set `onExpiry` (`close` default, or `reject`; merge `stricter`, order `close` → `reject`) (HITL-081).

## Amendment 2026-10-31 — from Area 7

- CFG-090, CFG-092: the provisional `context` field is replaced by the structured `context` block (CTX-100), which policy bundles may also declare. `compaction.model` and `retrieval.source` are `locked`.
- CFG-031 gains strictness orders: compaction mode `none` → `truncate` → `summarize`; automatic retrieval `false` → `true` (CTX-102).
- CFG-042 / CFG-071: a retrieval tool listed in `trustedTools` is a configuration error (CTX-021).

## Amendment 2026-10-31 — from Area 9

- CFG-090, CFG-092: the provisional `model` field is replaced by the structured `model` block (PROV-020), also allowed in policy bundles and personas. `provider` and `name` are `locked`; `fallbacks` are owned by the pinning layer (PROV-021); `params.maxOutputTokens` is `min`; other `params` are limited to adapter-declared generation parameters (PROV-022), narrowing the CFG-033 exemption.
- CFG-070: sensitivity policies gain an optional `providerRequirement` CEL condition over provider attributes; provider regions must satisfy `dataResidency` (PROV-012).
- CFG-110: a deployment also declares providers (endpoint, region, data-handling attributes) and an optional price table (PROV-010, PROV-072).

## Amendment 2026-10-31 — from Area 8

- CFG-090: harness profiles may set `delegation.maxDepth` (merge `min`, default 2) (ORCH-030).
- CFG-042: agent tools must declare `mutating`/`egress` if any reachable tool is; an agent tool's `output` requires a compatible child output schema; agent tools may not be listed in `trustedTools`; cost budgets require pricing for every model reachable through delegation (ORCH-020–023).
- CFG-091: a child's token and cost usage also counts toward its parent's turn budget (ORCH-042).

## Amendment 2026-11-01 — from Phase 4 review

- CFG-110: a deployment declares `attachmentSources`, the channel names hosts may give for attachments (CORE-121). `trustedAttachmentSources` (CFG-070) may list only declared names.

## Amendment 2026-11-01 — from Phase 4 (Areas 2–3 schemas and fixtures)

Writing schemas and fixtures for these areas exposed the gaps below. They are approved with the Phase 4 Areas 2–3 pull request.

**Errors and fields**
- **CFG-032**: the configuration error's `details` **MUST** include `artifact` (id@version), `field` (a JSON Pointer, RFC 6901, into that artifact, e.g. `/budget/tokens`), and `layer` (`policyBundle`, `persona`, `harnessProfile`, or `overlay`). Run-request violations (CFG-101) are `invalid_input` errors, not configuration errors, and carry `details.field` as a JSON Pointer into the profile.
- **CFG-033** is annotated *(untestable)* for implementation fixtures; the spec's CI enforces it on the schemas.
- **CFG-070**: the policy bundle field is renamed **`policyInstructions`** (merge `union`), so no field path has different merge rules in different kinds. Persona `instructions` stays `locked`. The two are separate fields and both reach the model (CTX-010).
- **CFG-030, maps**: map-valued fields merge per key. Any layer **MAY** add keys; a key a higher layer set keeps its value's merge rule. The schema annotates the map `union` and each value with its own rule.
- **HITL-023 in configuration**: `allowSelfApproval` **MUST NOT** have keys `taint` or `recovery`; such a key is a configuration error.
- **Secrets in bindings**: provider, port, MCP-server, and remote-hook bindings take secrets only in a `credentials` map of secret references. `extensions` **MUST NOT** carry secret values.

**Loading and snapshots**
- **CFG-042**: semantic checks apply to each persona combined with each profile in its `allowedProfiles`, with the full policy bundle stack. An artifact not reachable from any persona is checked on its own.
- **Defaults**: schema defaults (e.g. `deliveryMode: buffered`, `onExpiry: close`) apply after all layers merge. They are not a layer value, so a run request tightens relative to the effective value, defaults included. A merge-annotated field that no layer sets therefore takes its default only in the merged view; the snapshot leaves it absent (CFG-050, as amended 2026-11-14).
- **CFG-050**: the **effective configuration snapshot** is the validated set of artifacts after overlays, with schema defaults filled in, except for fields that carry a merge rule (`x-agentry-merge`), and with secret references unresolved. Merged views (persona × profile × run request) are computed from it deterministically and are not part of the snapshot. The **snapshot hash** is `sha256:` followed by the SHA-256 of the RFC 8785 canonical JSON (EVAL-000) of an object whose keys are artifact kinds, each holding its artifacts sorted by id then version.
- **JSON-compatible values**: configuration **MUST** use only JSON-compatible YAML values — strings, booleans, null, arrays, objects, and numbers within I-JSON's range (RFC 7493). Implicit YAML types such as dates or `yes`/`no` booleans are configuration errors. This makes the snapshot hash identical across implementations.
- **PORT-050**: a snapshot is written to a tenant's snapshot store when the first session for that tenant is created against it.

**Run requests**
- **CFG-101** (as amended 2026-11-14): run requests **MAY** tighten exactly these profile fields. Every other field, and any value that is not a tightening, is `invalid_input`.
  - **Run-scoped:** `stepLimit`, `budget.tokens`, `budget.cost`, `timeouts.run`, `timeouts.tool`, `retry.unavailable`, `outputRetryLimit`, `deliveryMode`, `checkpoint`, `trace.includeReasoning`, `limits.partSize`, `context.reserveOutputTokens`, `context.compaction.mode`, `context.compaction.triggerPercent`, `context.retrieval.auto`, `context.retrieval.limit`.
  - **Session-scoped:** `idleTtl`, `suspendedTtl`, `onExpiry`, `limits.sessionSize`, `delegation.maxDepth`. Only the run request that creates the session may tighten these, and they are recorded on `session.created` (CFG-102).
- **CFG-101**: run-request values use harness profile field paths (e.g. `{budget: {tokens: 500}}`).

**Environment overlays** (CFG-021, CFG-112)
- An overlay has an environment name, deployment values, and per-artifact behavioural values applied last, which may only tighten. Its file format is left to implementations; fixtures use the form in the fixture schema.
- An overlay **MAY** change endpoints, adapters, regions (subject to `dataResidency`), and port bindings. It **MUST NOT** loosen deployment governance: it may only append policy bundles, only remove `attachmentSources`, only add legal holds, and only lengthen retention periods.

## Amendment 2026-11-14 — where session-scoped overrides are recorded (post-Phase 4 review)

Requirement text above has been edited where noted.

- **CFG-102** (text above edited). The 2026-11-01 reading of CFG-101 added session-scoped fields: `idleTtl`, `suspendedTtl`, `onExpiry`, `limits.sessionSize` and `delegation`. Only the session-creating run request may tighten them, and the reading recorded them on `session.created`. CFG-102 still said every run-request value applies to that run only and is recorded on `run.started`, and `cfg.run-request-delegation-onexpiry` followed CFG-102. An implementation could satisfy one and fail the other. One following the fixture left `session.created.overrides` empty, so rebuilding a session from its event log (PORT-034) could not recover its effective session-scoped values, which the checkpoint does not hold.
- **Now** each value is recorded once, on the event of the scope it applies to:
  - `session.created.overrides` holds the session-scoped values;
  - `run.started.overrides` holds the run-scoped values.

  The session-creating request is split between the two. A request with only session-scoped values gives a `run.started` without `overrides`.
- **Fixtures.** `cfg.run-request-delegation-onexpiry` asserts the creating request's `onExpiry` and `delegation` on `session.created` and their absence from `run.started`.

## Amendment 2026-11-14 — merged fields keep no defaults in the snapshot (post-Phase 4 review)

Readings above have been edited where noted.

- **CFG-050, "Defaults".** The snapshot filled in schema defaults, and merged views are computed from the snapshot. The "Defaults" reading also says defaults "are not a layer value". Once a default was filled into a layer, it could not be told apart from a value its author had set, so it merged as a layer value. Results differed between implementations that merged from the filled snapshot and those that did not:
  - **`min` fields:** a bundle silent on `context.compaction.triggerPercent` became `90`, so a profile's `95` merged to 90. `context.retrieval.limit` behaved the same way.
  - **`approvalDefault`:** a silent upper bundle became `escalate` and overrode a lower bundle's `continue`. HOOK-133 (amendment 2026-11-13) relies on a silent bundle imposing nothing, and on an organisation setting `escalate` explicitly to forbid `continue` lower down.
  - **`stricter` fields whose default is mid-order** (`context.compaction.mode`): a silent bundle filled with `truncate` would have forbidden a profile's `summarize`.
- **Now** the snapshot fills every schema default except those of fields that carry `x-agentry-merge`. Such a field stays absent when its author did not set it. Its default applies to the merged view only, after every layer including the run request. Filling still happens only within objects present in the artifact (Area 11 amendment 2026-11-02). Defaults of fields that carry no merge rule are filled as before, for example a tool's `approval` and `idempotent`, and a hook's `failureMode`.
- **Hashes.** Snapshots that filled such defaults now hash differently. The golden bundles had `onExpiry: close` filled into every profile and `context.compaction.triggerPercent: 90` filled into one. Both were removed and the bundles re-hashed, and the replay fixtures that assert those hashes were updated.
- **Fixtures.** New: `cfg.merged-defaults-not-layer-values`.

## Amendment 2026-11-14 — the run-request field list (post-Phase 4 review)

Readings above have been edited where noted.

- **CFG-101** (reading above replaced). Three statements disagreed:
  - ADR-0007 allowed run requests to tighten `min`, `stricter` and `intersect` fields;
  - CFG-101 allowed `min` and `stricter` profile fields only;
  - the reading listed run-scoped and session-scoped fields.

  The lists left out `checkpoint` and `trace.includeReasoning`, which are `stricter` and which `cfg.strictness-orders-run-request` accepts in run requests. They also named `context` whole, although it holds `locked` and `union` fields that `context.config-context-run-request` rejects.
- **Now** the reading lists every field a run request may set, each as run-scoped or session-scoped. It is CFG-101's `min` and `stricter` profile fields, with one exception: `guardrails.requireDeterministic` is excluded because it is a load-time validity rule (HOOK-104), not run behaviour. `checkpoint` and `trace.includeReasoning` are run-scoped. `intersect` fields, including `model.fallbacks`, are not settable: a per-run narrowing of routing has no use case, and the eval matrix chooses models per cell (EVAL-044). ADR-0007 carries a note to this effect.
- **Fixtures.** `cfg.run-request-tighten-only` gains `guardrails.requireDeterministic` and `model.fallbacks`, both rejected.
