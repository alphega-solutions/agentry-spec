# Area 1 — Core model

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `domain.md` (approved, incl. amendment); notes `core.md`, `content.md`, `security.md` (settled); ADR-0002, 0003, 0005, 0008, 0009, 0010, 0014, 0015

---

## 1. Scope

This area specifies sessions, runs, turns, and steps; messages and content parts; structured output; events and their ordering; run end reasons; and the error model. Other areas build on these definitions.

Out of scope here, specified elsewhere: configuration loading (Areas 2–3), tool execution (Area 4), hooks and the taint rule (Area 5), escalation and decisions (Area 6), context assembly (Area 7), provider adapters (Area 9), storage ports (Area 10).

## 2. Conventions

- The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in bold capitals.
- Each normative requirement has an ID (`CORE-nnn`). Conformance fixtures reference these IDs.
- Terms are used exactly as defined in `domain.md`.
- "Implementation" means a conforming agentry implementation.

## 3. Identifiers and time

- **CORE-001** Session, run, and event IDs **MUST** be UUIDv7 (ADR-0010).
- **CORE-002** Timestamps **MUST** be RFC 3339 in UTC.
- **CORE-003** Implementations **MUST NOT** use timestamps to order events. Order is defined only by sequence number (§9.2).

## 4. Sessions

### 4.1 Creation

- **CORE-010** A session **MUST** be created with a principal, a persona reference, and an effective configuration snapshot. The tenant is taken from the principal.
- **CORE-011** Creating a session without a principal **MUST** fail with error category `invalid_input`. There is no anonymous session (ADR-0014).
- **CORE-012** A session's principal, tenant, persona, and snapshot hash **MUST NOT** change for the life of the session, including across `resume()`.
- **CORE-013** Creating a session **MUST** emit `session.created` as the session's first event. A new session is `idle`, waiting for its first input.

### 4.2 States

A session is in exactly one state.

| State | Meaning |
|---|---|
| `active` | A run is in progress |
| `idle` | Waiting for the principal's next input |
| `suspended` | Waiting for a human decision on an escalation |
| `closed` | Terminal. Records a close reason: `completed`, `cancelled`, `failed`, `expired` |

- **CORE-020** Transitions **MUST** follow this table. Any other transition is invalid.

| From | Trigger | To |
|---|---|---|
| (creation) | Session created | `idle` |
| `active` | Run ends with `responded`, `blocked`, `step_limit`, `budget_exhausted`, or `timeout` | `idle` |
| `active` | Run ends with `escalated` | `suspended` |
| `active` | Run ends with `cancelled` | `closed` (`cancelled`) |
| `active` | Run ends with `failed` | `closed` (`failed`) |
| `idle` | `run()` with new input | `active` |
| `idle` | `close()` | `closed` (`completed`) |
| `suspended` | `close()` | `closed` (`cancelled`) |
| `idle` | `idleTtl` elapses | `closed` (`expired`) |
| `suspended` | `resume()` with a decision | `active` |
| `suspended` | `suspendedTtl` elapses | `closed` (`expired`) |
| `idle`, `suspended` | `cancel()` | `closed` (`cancelled`) |

- **CORE-021** A closing transition **MUST** emit `session.closed` with the close reason. No event may follow it.
- **CORE-022** Operations on a closed session **MUST** fail with error category `conflict`, except a replayed `resume()` (CORE-053).

### 4.3 Concurrency

- **CORE-030** At most one run **MUST** be active per session.
- **CORE-031** A `run()` or `resume()` call on an `active` session **MUST** fail with error category `conflict` and **MUST NOT** affect the active run.
- **CORE-032** Implementations **MUST** enforce CORE-030 through the checkpoint's version (optimistic concurrency), so it holds across processes.

### 4.4 Expiry

- **CORE-040** A harness profile **MUST** set `idleTtl` and `suspendedTtl`. A profile without either is a configuration error. There is no default.
- **CORE-041** An expired session **MUST** be closed with reason `expired`. Implementations **MAY** detect expiry lazily (on next access) but **MUST** report the session as closed once its TTL has elapsed.

## 5. Runs

### 5.1 Starting a run

- **CORE-050** A run begins when a call to `run()` (new principal input) or `resume()` (a human decision on a suspended session) is accepted.
- **CORE-051** `run()` **MUST** be accepted only on an `idle` session. On a `suspended` session it **MUST** fail with error category `conflict`.
- **CORE-052** `resume()` **MUST** be accepted only on a `suspended` session, except as provided in CORE-053. On an `idle` session it **MUST** fail with error category `conflict`.
- **CORE-053** A `resume()` carrying a decision ID that has already been applied **MUST** return the original outcome without performing any new work, regardless of the session's current state. Such a replay is not a new run and **MUST NOT** emit events.
- **CORE-055** `resume()` **MUST** fail with error category `not_found` (code `agentry.config.snapshot_unavailable`) if the session's pinned snapshot cannot be retrieved. It **MUST NOT** fall back to the current configuration.
- **CORE-054** Each run **MUST** emit `run.started` before any other event of that run.

### 5.2 Ending a run

- **CORE-060** Every run **MUST** end with exactly one `run.ended` event carrying one run end reason.

| Run end reason | Cause |
|---|---|
| `responded` | The turn produced a response |
| `escalated` | A hook, policy decision, or tool approval requires a human |
| `blocked` | A guardrail blocked the turn at a point where it cannot continue (see §10) |
| `step_limit` | Steps in the turn exceeded the profile limit |
| `budget_exhausted` | The token or cost budget was reached |
| `timeout` | The wall-clock limit was reached |
| `cancelled` | `cancel()` was called or the event stream was abandoned |
| `failed` | An unrecoverable error occurred |

- **CORE-061** The resulting session state **MUST** follow CORE-020.

### 5.3 Cancellation

- **CORE-070** `cancel()` on an `active` session **MUST** stop further model and tool calls, persist a consistent checkpoint, and end the run with `cancelled`.
- **CORE-071** A consumer abandoning a run's event stream **MUST** be treated as `cancel()` (ADR-0005).
- **CORE-072** A tool call already in progress when cancellation occurs **MUST** receive the cancellation signal. Its outcome, if any, **MUST** be recorded before the run ends.

## 6. Turns and steps

- **CORE-080** A turn begins with principal input (`run()`) and ends when the agent responds or the session leaves `active` for any state other than `suspended`. A `resume()` continues the suspended turn; it starts a new run but not a new turn, and **MUST NOT** emit `turn.started`.
- **CORE-081** A step is one model call plus the tool calls requested by that call's response. Parallel tool calls requested by one response belong to the same step.
- **CORE-082** Turns are numbered from 1 within a session. Steps are numbered from 1 within a turn. A `resume()` continues the suspended turn's numbering.
- **CORE-083** When a turn's step count would exceed the profile's step limit, the implementation **MUST NOT** start the next step and **MUST** end the run with `step_limit`.

## 7. Messages and content

### 7.1 Messages

- **CORE-100** A message **MUST** have one role — `system` (persona and policy instructions), `principal`, `assistant` (the model), or `tool` — and an ordered, non-empty list of content parts.

### 7.2 Content parts

| Part type | Holds |
|---|---|
| `text` | Plain text |
| `image` | An image, by blob reference |
| `file` | A document, by blob reference |
| `structured` | A JSON value conforming to a declared schema |
| `tool_call` | Tool name, arguments, call ID |
| `tool_result` | Tool result (ok or error), call ID |
| `reasoning` | Provider reasoning content, possibly opaque |

- **CORE-110** The part types above are the complete set. Implementations **MUST** reject any other part type with error category `invalid_input`. Adapter-specific data **MUST** be placed in `extensions`.
- **CORE-111** Every part **MUST** carry a provenance and a (possibly empty) set of sensitivity labels.
- **CORE-112** `image` and `file` parts **MUST** carry a media type and a blob reference, and **MUST NOT** carry inline binary data. A part that violates this **MUST** be rejected with error category `invalid_input`.
- **CORE-113** A blob reference **MUST** include an ID, content hash, media type, and size, and **MUST** be scoped to the session's tenant. Resolving a blob reference from another tenant **MUST** fail with error category `not_found`.
- **CORE-114** A part **MUST NOT** reference an external URL for retrieval; such a part **MUST** be rejected with error category `invalid_input`. Hosts ingest content into the BlobStore first.
- **CORE-115** A part exceeding the profile's per-part size limit, or a part that would take the session's total content size over the per-session limit, **MUST** be rejected with error category `invalid_input`.

### 7.3 Provenance of content

- **CORE-119** Content from persona and policy instructions **MUST** have provenance `system` and is trusted.
- **CORE-120** Text typed by the principal **MUST** have provenance `principal`. It is trusted as a request, never as policy.
- **CORE-121** `image` and `file` parts supplied with a request (attachments) **MUST** carry provenance `attachment:<source>`, where `<source>` is the channel the host declares (e.g. `upload`). They **MUST** be untrusted, regardless of who supplied them, unless a policy bundle lists their source in `trustedAttachmentSources`.
- **CORE-122** Content derived from a part (for example, text extracted from a file) **MUST** inherit that part's provenance and labels.
- **CORE-123** Until a hook labels it, an attachment **MUST** carry the harness profile's default attachment labels.
- **CORE-124** Parts produced by a tool **MUST** have provenance `tool:<name>` and carry the tool's sensitivity labels; they are untrusted unless a policy bundle marks the tool `trustedOutput: true`.

### 7.4 Content and hooks

- **CORE-125** Hooks **MUST** receive binary parts as blob references, not bytes. A hook needing the bytes reads them through the BlobStore port.
- **CORE-126** A hook `rewrite` **MAY** change `text` and `structured` parts and **MAY** remove or replace a binary part. It **MUST NOT** modify binary content in place.
- **CORE-127** A hook `annotate` **MAY** add sensitivity labels to individual parts.

The consequences of provenance and taint for tool calls are specified in Area 5. Limits on how much history the model sees are set by the context manager (Area 7); the core guarantees only that events are complete and ordered.

## 8. Structured output and reasoning

### 8.1 Structured output

- **CORE-130** When the persona or harness profile declares an output schema, a `responded` run's final assistant message **MUST** contain a `structured` part that validates against it. It **MAY** also contain `text` parts.
- **CORE-131** A profile that declares an output schema and `streamed` delivery **MUST** be rejected as a configuration error.
- **CORE-132** If the model's output fails validation, the implementation **MUST** request a correction, up to the profile's retry limit. Each correction is a step and counts toward the step limit and budget.
- **CORE-133** If the retry limit is reached, the run **MUST** end `failed` with error code `agentry.output.schema_mismatch` (category `fatal`).
- **CORE-134** Schema validation **MUST** complete before `beforeResponse` hooks run, and those hooks **MUST** receive the validated value.

### 8.2 Reasoning parts

- **CORE-140** `reasoning` parts **MUST** be stored in the checkpoint.
- **CORE-141** `reasoning` parts **MUST NOT** be included in the response delivered to the principal by default.
- **CORE-142** `reasoning` parts **MUST NOT** be sent to a provider other than the one that produced them.
- **CORE-143** `reasoning` parts **MUST** be excluded from traces unless the profile includes them, in which case they are labelled and redacted like any content.

## 9. Events

### 9.1 Envelope

- **CORE-150** Every persisted event **MUST** carry these fields:

| Field | Requirement |
|---|---|
| `schemaVersion` | Contract version of the event |
| `eventId` | UUIDv7 |
| `sessionId`, `runId` | `runId` absent only on `session.created` and on a `session.closed` that occurs outside a run (expiry, `close()`, or `cancel()` of an idle or suspended session) |
| `seq` | Per §9.2 |
| `turn`, `step` | Present where applicable |
| `type` | One of the catalog types (§9.3) |
| `timestamp` | Per CORE-002 |
| `tenantId` | The session's tenant |
| `principalRef` | A reference to the principal; **MUST NOT** contain the full principal |
| `snapshotHash` | The session's snapshot hash |
| `traceContext` | W3C Trace Context identifiers |
| `payload` | Type-specific body |
| `extensions` | Optional; adapter or vendor data |

- **CORE-151** Events whose payload carries content **MUST** carry the provenance and sensitivity labels of that content.
- **CORE-152** Event payloads **MUST NOT** contain inline binary content.
- **CORE-153** Event payloads **MUST NOT** contain secret values.
- **CORE-154** Payloads larger than the implementation's inline limit **MUST** be stored in the BlobStore and referenced. Inline payloads **MUST** be redacted according to the sensitivity policies in force.

### 9.2 Ordering and persistence

- **CORE-160** Every persisted event **MUST** have a sequence number (`seq`) that is unique, strictly increasing, and gap-free within its session, across all runs.
- **CORE-161** Persisted events **MUST NOT** be modified.
- **CORE-162** Ephemeral events (`model.delta`) **MUST** carry the envelope without `seq` and **MUST NOT** be persisted, traced, or checkpointed.
- **CORE-163** If `model.delta` events are emitted for a model response, their concatenated content **MUST** equal the content of the corresponding `model.response`.

### 9.3 Catalog

- **CORE-170** Implementations **MUST** emit only the event types below. New types require a spec change; additional data **MUST** go in `extensions`.

| Type | Emitted when | Persisted |
|---|---|---|
| `session.created` | A session is created | Yes |
| `session.closed` | A session closes; carries the close reason | Yes |
| `run.started` | A run begins; carries whether it is `run` or `resume` | Yes |
| `run.ended` | A run ends; carries the run end reason | Yes |
| `turn.started` | A turn begins | Yes |
| `turn.completed` | A turn ends | Yes |
| `model.request` | A request is sent to a provider | Yes |
| `model.response` | A complete response is received | Yes |
| `model.delta` | A token delta is received | **No** (ephemeral) |
| `tool.call` | A tool call is dispatched | Yes |
| `tool.result` | A tool result is received | Yes |
| `hook.decision` | A hook returns a result other than `continue` | Yes |
| `policy.decision` | The harness applies the taint rule, an assurance check, or a scope check | Yes |
| `checkpoint.saved` | A checkpoint is persisted | Yes |
| `escalation.raised` | A human decision is requested | Yes |
| `escalation.resolved` | A decision is applied | Yes |
| `error` | An error occurs that is not delivered as a tool result | Yes |

Payload schemas for each type are specified in Phase 4.

## 10. Blocks

When a hook or policy decision blocks, the effect depends on where it occurs. Hook semantics are specified in Area 5; the run-level outcome is fixed here.

- **CORE-180** Block outcomes **MUST** follow this table:

| Where the block occurs | Outcome |
|---|---|
| `sessionStart` or `beforeModelCall` | No model call is made; the run ends `blocked` |
| `afterModelCall` | The model output is discarded; the run ends `blocked` |
| `beforeToolCall`, or the taint rule, an assurance check, or a scope check on a tool call | The tool is not called; the model receives a `policy` error as that tool's result and the turn may continue |
| `afterToolCall` | The result is withheld; the model receives a `policy` error as that tool's result and the turn may continue |
| `beforeResponse` | The response is withheld; the run ends `blocked` |

- **CORE-182** Hooks at `onError` and `sessionEnd` cannot change a run's outcome. A hook definition at these points that declares `rewrite`, `block`, or `escalate` **MUST** be rejected as a configuration error.
- **CORE-181** When a run ends `blocked`, the principal **MUST** receive the fallback message declared in the persona, or the policy bundle default if the persona declares none. The fallback message **MUST NOT** be generated by a model.

## 11. Errors

- **CORE-190** Every error produced by a tool, hook, provider adapter, storage port, configuration loader, or the harness **MUST** have this shape (ADR-0009):

| Field | Requirement |
|---|---|
| `code` | Stable, namespaced identifier (e.g. `agentry.tool.timeout`) |
| `category` | One of the categories below |
| `retryable` | Boolean |
| `source` | `tool`, `hook`, `provider`, `port`, `harness`, or `config` |
| `message` | Human-readable; **MUST NOT** contain sensitive content |
| `details` | Optional structured data, subject to sensitivity labels and redaction |

- **CORE-191** The category **MUST** be one of:

| Category | Meaning | Required handling |
|---|---|---|
| `invalid_input` | Bad arguments or request | Returned to the model or caller to correct |
| `unauthorized` | Principal lacks rights or assurance | Not retried; may escalate |
| `policy` | Blocked by a guardrail or policy decision | Not retried; outcome per §10 |
| `limit` | Budget, step limit, or timeout reached | Run ends with the matching reason |
| `unavailable` | A dependency is temporarily down | Retried per profile; then treated as `fatal` |
| `conflict` | Concurrent run, closed session, or version mismatch | Returned to the caller |
| `not_found` | Missing resource, including another tenant's | Returned to the caller |
| `configuration` | Invalid configuration | Load-time; nothing loads |
| `cancelled` | Work stopped by cancellation | Run ends `cancelled` |
| `fatal` | Unrecoverable | Run ends `failed` |

- **CORE-192** Implementations **MUST** decide handling by category, never by parsing `message` or `code`.
- **CORE-193** Access to another tenant's resource **MUST** produce `not_found`, never a distinct authorization error.
- **CORE-194** Provider and vendor errors **MUST** be mapped into this shape. Original vendor detail **MAY** be placed in `details`, subject to redaction.

## 12. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Single turn, no tools → `responded`, session `idle` | CORE-020, 054, 060 |
| Multi-step turn with parallel tool calls → correct turn, step, seq numbering | CORE-081, 082, 160 |
| `seq` gap-free across several runs and a resume | CORE-160 |
| Session without principal → rejected | CORE-011 |
| Principal, persona, snapshot unchanged across resume | CORE-012 |
| Concurrent `run()` on active session → `conflict`, active run unaffected | CORE-030, 031 |
| `run()` on suspended session → `conflict` | CORE-051 |
| Replayed `resume()` decision → original outcome, no new events, also on a closed session | CORE-053, 022 |
| `resume()` on idle session → `conflict` | CORE-052 |
| `resume()` with pinned snapshot missing → `not_found`, no fallback | CORE-055 |
| New session is `idle`; `session.created` is first event | CORE-013 |
| `close()` on idle → `completed`; on suspended → `cancelled`; no events after `session.closed` | CORE-020, 021 |
| Resume continues the suspended turn without `turn.started` | CORE-080, 082 |
| Each run end reason → correct session state | CORE-020, 060, 061 |
| Operation on closed session → `conflict` | CORE-022 |
| Idle and suspended TTL expiry → `closed` (`expired`) | CORE-040, 041 |
| Profile missing a TTL → configuration rejected | CORE-040 |
| Abandoned stream → run `cancelled`, consistent checkpoint | CORE-070, 071 |
| Step limit reached → `step_limit`, next step not started | CORE-083 |
| Unknown part type → `invalid_input` | CORE-110 |
| Image part: blob reference only, no inline bytes in events | CORE-112, 152 |
| Blob reference from another tenant → `not_found` | CORE-113, 193 |
| Part with external URL → rejected | CORE-114 |
| Oversized part → `invalid_input` | CORE-115 |
| Attachment untrusted; derived text inherits provenance | CORE-121, 122 |
| Attachment with injected instruction → turn tainted; mutating call escalates (with Area 5) | CORE-121 |
| Tool-produced part carries `tool:<name>` provenance and tool labels | CORE-124 |
| Hook receives blob reference; replaces binary part; in-place edit rejected; annotate labels a part | CORE-125–127 |
| Unscanned attachment carries default labels | CORE-123 |
| Output schema met; corrected within limit; limit reached → `failed` | CORE-130, 132, 133 |
| `streamed` profile with output schema → configuration rejected | CORE-131 |
| `beforeResponse` hook receives validated structured value | CORE-134 |
| Reasoning kept in checkpoint, absent from trace and response, not sent to another provider | CORE-140–143 |
| Deltas unsequenced, not persisted, concatenate to response | CORE-162, 163 |
| Unknown event type never emitted | CORE-170 |
| Block at each location → outcome per table | CORE-180 |
| Blocked run returns persona fallback, else policy default | CORE-181 |
| Error message free of labelled content | CORE-190 |
| Vendor error mapped to error shape | CORE-194 |
| IDs are UUIDv7; timestamps RFC 3339 UTC; reordered timestamps do not change order | CORE-001–003 |
| Concurrent runs from two processes → one `conflict` | CORE-032 |
| Cancel during an in-flight tool call → tool receives signal, outcome recorded | CORE-072 |
| Empty message → `invalid_input` | CORE-100 |
| Envelope fields present; `principalRef` only; no binary, no secrets; large payload by reference | CORE-150–154 |
| Persisted event never changes | CORE-161 |
| Category drives handling regardless of message text; wrong tenant → `not_found` | CORE-191–193 |
| `onError` hook declaring `block` → configuration rejected | CORE-182 |

## 13. Additions approved with this spec (2026-10-31)

These requirements went beyond the settled notes and ADRs and were approved with this spec.

| ID | Proposed rule |
|---|---|
| CORE-011 | Missing principal fails with `invalid_input` |
| CORE-013 | `session.created` is first; a new session starts `idle` |
| CORE-020 | New `close()` operation: idle → `completed`, suspended → `cancelled`; `cancel()` closes idle and suspended sessions |
| CORE-021 | No event follows `session.closed` |
| CORE-022 | Operations on a closed session fail with `conflict` |
| CORE-031 | A rejected concurrent call never affects the active run |
| CORE-041 | Expiry may be detected lazily |
| CORE-051, 052 | `run()` on suspended and `resume()` on idle fail with `conflict` |
| CORE-053 | A replayed decision returns the original outcome in any state and emits no events |
| CORE-055 | Missing pinned snapshot fails with `not_found` (`agentry.config.snapshot_unavailable`) |
| CORE-072 | An in-flight tool receives the cancellation signal; its outcome is recorded |
| CORE-080 | A resume continues the suspended turn without `turn.started` |
| CORE-100 | Messages must have at least one part |
| CORE-110 | Unknown part types fail with `invalid_input` |
| CORE-150 | When `runId` may be absent |
| CORE-170 | `run.started` records run vs resume; `error` events cover errors not delivered as tool results |
| CORE-181 | **Reconciliation:** the fallback message is returned whenever a run ends `blocked`, including input-side blocks (`sessionStart`, `beforeModelCall`, `afterModelCall`). `domain.md` currently describes it only for output guardrails; approving this amends that definition. |
| CORE-182 | Hooks at `onError` and `sessionEnd` may not declare `rewrite`, `block`, or `escalate` |
| CORE-191 | `invalid_input` returns to the model or the caller (callers also send bad requests); `conflict` includes closed sessions |

## Amendment 2026-10-31 — from Area 6

- **CORE-020** gains one transition: `suspended`, `suspendedTtl` elapses, profile `onExpiry: reject`, and no undecided recovery action → remains `suspended` with every pending action decided by expiry rejection. From there, `resume()` → `active`; a further `idleTtl` without `resume()` → `closed` (`expired`) (HITL-082).
- **CORE-030–032**: an active run holds a renewable lease. A run whose lease lapses is orphaned; orphaned runs are ended through recovery (HITL-090, HITL-091), and `run()`/`resume()` on a session with an orphaned run perform recovery instead of failing with `conflict` (HITL-092).
- **Operations**: `decide()` records decisions without resuming (HITL-040).

## Amendment 2026-10-31 — from Area 7

- **CORE-170** event catalog gains two persisted types: `context.retrieved` (an automatic retrieval, CTX-032) and `context.compacted` (a compaction, CTX-082).
- **CORE-060 / CORE-020** run end reasons gain `context_limit`: context cannot fit after compaction; session → `idle` (CTX-090).
- **CORE-154**: content needed to reproduce context (retrieved content, summaries) is stored in full in the BlobStore and referenced; the event's inline view may be redacted (CTX-003).

## Amendment 2026-10-31 — from Area 9

- **CORE-180** block locations gain: no allowed model for the content in context (PROV-052), and a provider safety refusal returned as an error (PROV-081). Both end the run `blocked` with the fallback message.
- **CORE-170** `policy.decision` also records sensitivity-routing switches and denials (PROV-051, PROV-052).
- `run()` with attachments no allowed model supports is rejected with `invalid_input` before a run starts (PROV-042).

## Amendment 2026-10-31 — from Area 8

- **CORE-120**: in a child session, the first `principal`-role message carries the parent's least-trusted provenance and labels, not `principal` (ORCH-011).
- **CORE-191**: delegation error results (`agentry.delegation.*`) are delivered to the parent model and never end the parent run by themselves (ORCH-051).
- **CORE-020 / CORE-040–041**: sessions in a delegation chain suspend together, expire at the chain's earliest TTL with its strictest `onExpiry`, and close deepest-first when a parent closes (ORCH-060, 065, 066, 070). Host operations on child sessions are refused with `conflict` (ORCH-006).

## Amendment 2026-10-31 — from Area 11

- **CORE-001–003**: implementations obtain time and IDs (including UUIDv7 time components) from an injectable clock and seedable ID generator (EVAL-034).
- All areas: a requirement may be annotated *(untestable)* with a reason; every other normative requirement must be covered by a conformance fixture (EVAL-010).

## Amendment 2026-11-01 — from Phase 4 review (approved with the Phase 4 Area 1 pull request)

Writing schemas and fixtures for this area exposed these gaps. Requirement text above has been edited where noted.

- **CORE-112, CORE-114** now name their error category: `invalid_input`.
- **CORE-121** attachments carry a new provenance value, `attachment:<source>`, which `trustedAttachmentSources` matches. This adds one value to the provenance list in `domain.md` §7.
- **CORE-121 — declaring the source.** The host **MUST** state the source of each attachment it passes to `run()`, as a channel name (e.g. `upload`, `email`). Channel names **MUST** be declared in the deployment's `attachmentSources` list *(extends CFG-110)*. An attachment with no source, or an undeclared one, **MUST** be rejected with `invalid_input` (`agentry.content.attachment_source`) before a run starts. The implementation sets the part's provenance to `attachment:<source>`; a host cannot supply any other provenance.
- **CORE-131, CORE-161, CORE-182** reworded with **MUST**, so they are normative and covered by fixtures.
- **CORE-191** `unauthorized` covers the principal lacking rights in the host's authorization; a principal below a tool's `minAssurance` produces `policy` (CORE-180, TOOL pipeline stage 4). The table's "or assurance" is withdrawn.
- **CORE-191** `not_found` and `conflict` errors returned by a **tool** are delivered to the model as tool results, like `invalid_input`; "returned to the caller" applies to host operations only.
- **CORE-020** `close()` on an `active` session **MUST** fail with error category `conflict`.
- **CORE-040/041** a TTL has elapsed when the current time is equal to or later than the expiry time.
- **CORE-150/170** `model.response` is persisted after `afterModelCall` hooks, and records the response as those hooks left it, with any labels they added (consistent with TOOL-073 for tool results).

## Amendment 2026-11-02 — from Phase 4 (Area 11)

- **CORE-170** event catalog: the `turn.started` payload is `{message}`, the principal's message as it enters context — on the first turn, after the `sessionStart` hooks — with its provenances and labels (`schemas/core/v1/event.yaml`). `turn.started` is a content event for CORE-151: it carries `provenances` and `labels`. See the Area 11 amendment 2026-11-02 (CTX-001, EVAL-025).

## Amendment 2026-11-01 — from Phase 4 (Area 4)

- **CORE-191** `unavailable`: for errors returned by a **tool**, handling follows TOOL-052/053 as amended — non-retryable tool errors are delivered to the model; retryable ones are retried, or treated as `fatal` when they may not be retried or retries are exhausted. The "then treated as `fatal`" rule applies to provider, port, and harness errors.

