# Area 7 — Context and retrieval

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `domain.md` (approved, incl. context amendment); notes `context.md`, `security.md`, `content.md` (settled); ADR-0008, 0014, 0015; Areas 1–6 (approved)

---

## 1. Scope

This area specifies how the context manager assembles what the model sees at each step, how retrieved content enters context, how context is compacted to fit a model's limit, and what happens when it cannot fit.

Specified elsewhere: a model's context limit is a provider capability (Area 9); the vector store port (Area 10). Cross-session memory is not part of the 1.0 core; hosts provide it as ordinary tools (Area 4). Schemas for the profile `context` block and the `context.retrieved` and `context.compacted` event payloads are specified in Phase 4.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `CTX-`.

## 3. Context is a view

- **CTX-001** The context for a model call **MUST** be derived only from the session's events (including `context.retrieved` and `context.compacted`), their referenced blobs, and the snapshot, so it can be reproduced for replay.
- **CTX-002** Assembling or compacting context **MUST NOT** modify, remove, or reorder persisted events (CORE-161).
- **CTX-003** Content that context reproduction depends on (retrieved content, summaries) **MUST** be stored in full in the BlobStore and referenced from its event. The event's inline view may be redacted (CORE-154); the blob is tenant-scoped and subject to the same sensitivity policies as any content.

## 4. Assembly

- **CTX-010** For each model call, the context manager **MUST** assemble content in this order:
  1. **System content:** policy-bundle `instructions` in stack order, then persona `instructions` (provenance `system`).
  2. **Summaries**, oldest first (§6).
  3. **History:** messages from earlier turns not covered by a summary, oldest first.
  4. **Current turn:** the principal's message — its input and attachments, followed by any automatically retrieved content as additional parts (§5.2) — then this turn's assistant messages, tool calls, and tool results, in event order.
- **CTX-011** `beforeModelCall` hooks **MUST** see the assembled context as it will be sent, after any compaction (HOOK §4). This is where hooks inspect, label, or block automatically retrieved content.
- **CTX-012** The provider adapter formats the context for its provider and **MUST** delimit untrusted content (ADR-0008). Delimiting is defence in depth, not a security boundary.
- **CTX-013** `reasoning` parts **MUST** be included only when sent back to the provider that produced them (CORE-142).

## 5. Retrieval

### 5.1 Retrieval tools

- **CTX-020** A **retrieval tool** is a tool (Area 4) with `binding.kind: retrieval`, naming a vector store source. It **MUST** have `effect: read` and is scoped, hooked, and recorded like any other tool. *(Extends the Area 4 binding kinds.)*
- **CTX-021** Results of a retrieval tool **MUST** carry provenance `retrieval:<source>`, not `tool:<id>`. A retrieval tool listed in `trustedTools` is a configuration error: retrieved content is always untrusted (HOOK-120).

### 5.2 Automatic retrieval

- **CTX-030** Automatic retrieval is off unless enabled in the `context` block (§8).
- **CTX-031** When enabled, the context manager **MUST** query the configured source once per turn: after `sessionStart` hooks (on the first turn) and before the turn's first model call, using the principal's input as it stands after any hook rewrite. It includes up to `retrieval.limit` results. A `resume()` continues the turn and **MUST NOT** retrieve again.
- **CTX-032** Each automatic retrieval **MUST** emit a `context.retrieved` event recording the source, the query, and references to the results. *(Amends CORE-170: new persisted event type.)*
- **CTX-033** Automatically retrieved content is not a tool call and is not visible to the model as a tool.

### 5.3 Rules for all retrieved content

- **CTX-040** Retrieved content **MUST** have provenance `retrieval:<source>`. It is untrusted and taints the session when it enters context (HOOK-120), including when it is empty of sensitive data.
- **CTX-041** The vector store port **MUST** filter results by the session's tenant and by the principal's access rights inside the port, before results are returned (ADR-0014).
- **CTX-042** Retrieved content **MUST** carry the sensitivity labels stored with it. Retrieved content stored without labels **MUST** carry the profile's `retrieval.defaultLabels`.
- **CTX-043** Retrieval is additive: retrieved content **MUST NOT** replace or reorder system content or history.

## 6. Compaction

### 6.1 When

- **CTX-050** Before each model call, the context manager **MUST** compute the space available: the model's context limit minus `reserveOutputTokens`. If assembled context exceeds `compaction.triggerPercent` of that space, it **MUST** compact according to `compaction.mode`.

### 6.2 What may be dropped

- **CTX-060** Compaction **MUST NOT** drop or summarize:
  - system content;
  - the current turn's principal message (input, attachments, and automatically retrieved parts);
  - tool calls and results in the current step;
  - reasoning parts the provider requires for continuation (CORE-142).
- **CTX-061** Droppable content is compacted in whole units, in this order: existing summaries and earlier turns, oldest first; then earlier steps of the current turn, oldest first.
- **CTX-062** `summarize` **MAY** fold existing summaries into a new one, so summaries do not accumulate without limit.

### 6.3 Modes

| Mode | Effect |
|---|---|
| `none` | No compaction; if context does not fit, overflow (§7) |
| `truncate` | Remove droppable units in order until context fits |
| `summarize` | Replace droppable units in order with a summary until context fits |

- **CTX-070** `truncate` and `summarize` **MUST** remove or replace the minimum number of droppable units needed to fit.

### 6.4 Summaries

- **CTX-080** The summarizer **MUST** run as a model call with no tools. Its model **MUST** be from an allowed provider (CFG-070, CFG-080) and is subject to the sensitivity policies of the content it reads. Its calls **MUST NOT** pass through hooks or emit `model.request`/`model.response` events.
- **CTX-081** A summary **MUST** record the union of the provenances of the content it replaces and is treated with the least-trusted of them. It **MUST** carry the union of their sensitivity labels. Taint persists (HOOK-121), and the session keeps every tainting provenance (HOOK-126).
- **CTX-082** Each compaction **MUST** emit a `context.compacted` event recording: the mode, the units covered, a reference to the summary (for `summarize`), its provenances and labels, and the summarizer's token usage. *(Amends CORE-170: new persisted event type.)*
- **CTX-083** On replay, recorded summaries **MUST** be reused from their blobs, not regenerated.
- **CTX-084** Summarizer tokens **MUST** count toward the turn budget (CFG-091). If the budget is exhausted during summarization, the run **MUST** end `budget_exhausted`.
- **CTX-085** If the summarizer fails, or a sensitivity policy forbids sending the content to its provider, the context manager **MUST** fall back to `truncate` for that compaction and emit an `error` event (or `policy.decision`, for a policy denial). The fallback is never silent.

## 7. Overflow

- **CTX-090** If context cannot fit after compaction, or `compaction.mode` is `none` and context does not fit, the model call **MUST NOT** be made. The implementation **MUST** emit an `error` event (`limit`, `agentry.context.overflow`) and end the run with run end reason `context_limit`; the session moves to `idle`. *(Amends CORE-060, CORE-020, and the run end reasons in `domain.md` §2.)*

## 8. Configuration: the `context` block

This block replaces the provisional `context` field (CFG-090, CFG-092).

- **CTX-100** Policy bundles and harness profiles **MAY** declare a `context` block with these fields:

| Field | Merge rule | Default | Meaning |
|---|---|---|---|
| `reserveOutputTokens` | `min` | Provider default (Area 9) | Space kept for the response |
| `compaction.mode` | `stricter` (`none` → `truncate` → `summarize`) | `truncate` | How to compact; `none` is strictest because no model reads history |
| `compaction.triggerPercent` | `min` | 90 | Fill level that triggers compaction |
| `compaction.model` | `locked` | The session's model | Summarizer model; a policy bundle may pin it |
| `retrieval.auto` | `stricter` (`false` → `true`) | `false` | Enables automatic retrieval |
| `retrieval.source` | `locked` | — | Vector store source; required if `retrieval.auto` is `true` |
| `retrieval.limit` | `min` | 5 | Maximum results per automatic retrieval |
| `retrieval.defaultLabels` | `union` | empty | Labels for retrieved content stored without labels |

- **CTX-101** `retrieval.auto: true` without a `retrieval.source` is a configuration error.
- **CTX-102** The strictness orders above extend CFG-031.

## 9. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Same events, blobs, and snapshot → identical context | CTX-001 |
| Compaction leaves events unchanged | CTX-002 |
| Redacted event view, full blob used for reproduction | CTX-003 |
| Assembly order; retrieved parts appended to principal message | CTX-010 |
| `beforeModelCall` hook sees compacted context and can label retrieved content | CTX-011 |
| Untrusted content delimited in provider request | CTX-012 |
| Reasoning sent only to its own provider | CTX-013 |
| Retrieval tool: `effect: read`; results `retrieval:<source>`; in `trustedTools` → rejected | CTX-020, 021 |
| Automatic retrieval off by default; on: once per turn, after `sessionStart` rewrites, limited results | CTX-030, 031 |
| Resume does not retrieve again | CTX-031 |
| `context.retrieved` recorded; not shown to the model as a tool | CTX-032, 033 |
| Retrieved content untrusted, taints session, even with empty results containing no labels | CTX-040 |
| Retrieval filtered by tenant and principal rights in the port | CTX-041 |
| Stored labels carried; unlabelled results get `retrieval.defaultLabels` | CTX-042 |
| Retrieval never displaces system content or history | CTX-043 |
| Compaction triggered at the configured fill level | CTX-050 |
| Never-dropped content survives compaction | CTX-060 |
| Drop order: summaries and old turns, then earlier steps of current turn | CTX-061 |
| Summaries folded rather than accumulating | CTX-062 |
| Minimum units removed | CTX-070 |
| Summarizer: allowed provider, no tools, no hooks, no model events | CTX-080 |
| Summary records all provenances; least-trusted applies; labels unioned; taint persists | CTX-081 |
| `context.compacted` recorded; replay reuses summary blob | CTX-082, 083 |
| Summarizer tokens counted; budget exhausted during summary → `budget_exhausted` | CTX-084 |
| Summarizer failure or policy denial → truncate with recorded event | CTX-085 |
| Overflow → `error` event, `context_limit`, session `idle`, no model call | CTX-090 |
| Each `context` field: tighten accepted, loosen rejected; bundle pins summarizer model | CTX-100, 102 |
| Auto retrieval without source → rejected | CTX-101 |
| Memory write tool in a tainted session → escalation (with Areas 4–5) | X1 decision |

## 10. Additions approved with this spec (2026-10-31)

| ID | Proposed rule |
|---|---|
| CTX-001, 003 | Context reproducible from events, blobs, and snapshot; reproduction content stored in full in the BlobStore (clarifies CORE-154) |
| CTX-010 | Assembly order; **automatically retrieved content appended to the principal's message** |
| CTX-011 | Hooks see context after compaction |
| CTX-020, 021 | **New `retrieval` binding kind**; retrieval results always untrusted and never in `trustedTools` (extends Area 4) |
| CTX-031 | Automatic retrieval once per turn, after `sessionStart` rewrites; never again on resume |
| CTX-032, 033 | **New `context.retrieved` event** (amends CORE-170); automatic retrieval is not a tool call |
| CTX-042 | Stored labels carried; new `retrieval.defaultLabels` for unlabelled content |
| CTX-050 | Compaction trigger based on a fill percentage |
| CTX-060 | Attachments and retrieved parts of the current principal message are never dropped |
| CTX-061, 062, 070 | Drop order including earlier steps of the current turn; summaries may be folded; minimum removal |
| CTX-081 | Summaries record all provenances (aligns with HOOK-126) |
| CTX-082 | `context.compacted` event contents (amends CORE-170) |
| CTX-084 | Budget exhaustion during summarization ends the run `budget_exhausted` |
| CTX-085 | **Summarizer failure or policy denial falls back to truncation, with a recorded event** |
| CTX-090 | `context_limit` run end reason with an `error` event (amends CORE-060, CORE-020, `domain.md`) |
| CTX-100 | `context` block allowed in policy bundles too; fields, defaults (`truncate`, 90%, 5 results), merge rules; `compaction.model` and `retrieval.source` are `locked` |
| CTX-101, 102 | Auto retrieval requires a source; new strictness orders extend CFG-031 |

## Amendment 2026-10-31 — from Area 9

- CTX-050: compaction targets the smallest `contextLimit` among the primary model and its remaining fallbacks (PROV-044).
- CTX-060: required reasoning parts are protected only while the same provider continues; after a provider switch they are not sent (PROV-055).

## Amendment 2026-11-01 — from Phase 4 (Areas 2–3)

- CTX-010: "policy-bundle `instructions`" is now the bundle field `policyInstructions` (CFG amendment).

