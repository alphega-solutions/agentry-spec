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


## Amendment 2026-11-01 — from Phase 4 (schemas and fixtures)

Schemas: the `context.retrieved` and `context.compacted` payloads in `schemas/core/v1/event.yaml`; the `context` block in `schemas/config/v1/defs.yaml`; retrieval bindings in `schemas/config/v1/tool.yaml`.

**Trust order** (also used by HOOK-021 and ORCH-011)

- Provenances rank, most trusted first: `system`; `reviewer`; `principal`; `model`; trusted external content (`tool:` in `trustedTools`, `attachment:` in `trustedAttachmentSources`, `agent:` whose output is trusted); untrusted content (every other `tool:`, `attachment:` and `agent:`, and every `retrieval:`, HOOK-120). The **least-trusted** provenance of a set is its lowest-ranked one; ties go to the one that entered context first.

**Measuring context** (CTX-050, CTX-090)

- Context size is counted in tokens by the provider adapter of each candidate model (PROV-045); the context manager compacts until the context fits every candidate (PROV-044). Tool definitions are not part of the assembled context.

**Units** (CTX-061, CTX-070)

- An earlier **turn** unit is every message of that turn. A **step** unit of the current turn is one model response and its tool calls and results. A **summary** unit is an earlier summary. A unit is removed or summarized whole; `context.compacted` lists the units covered, in drop order.
- A summary is one `assistant`-role message with one text part, placed after system content in the order summaries were made (CTX-010). Its part has the least-trusted provenance of the content it replaces and the union of its labels; the event's `provenances` lists every provenance it replaces, in order of first entry (CTX-081). Folding (CTX-062) summarizes earlier summaries together with the units being dropped; a folded summary is a unit of the new one.
- The summarizer request carries no tools and only the content being summarized; its instructions are implementation-defined. Its usage is recorded on `context.compacted` and counts toward the turn budget (CTX-084).
- CTX-085: a fallback emits `context.compacted` with `mode: truncate` and `fallback: summarizer_failed` (with an `error` event, `source: provider`) or `fallback: policy_denied` (with a `policy.decision` of kind `summarizer`, outcome `block`).

**Retrieval**

- CTX-031: the automatic retrieval query is the text of the principal message's text parts, after hook rewrites, joined with a newline. The port is queried with the session's tenant and principal, the source, that text, and the effective `retrieval.limit`. Each result becomes one `text` part appended to the principal message, in the order the port returned them, with provenance `retrieval:<source>` and its labels (CTX-042).
- If the vector store fails during automatic retrieval, an `error` event is emitted (`source: port`), no `context.retrieved` is emitted, and the turn continues without retrieved content; nothing entered context, so the session is not tainted.
- CTX-020: a retrieval tool's `input` declares a required string `query` and may declare an integer `limit` (default 5). Its `ok` output is `{results: [{id, text}]}` in the port's order; its `tool_result` part carries provenance `retrieval:<source>` and the union of the results' labels (stored labels, or the profile's `retrieval.defaultLabels` for results stored without any).
- CTX-012: provider requests carry every part's provenance, which is what an adapter delimits by. Whether a given provider's formatting delimits untrusted content is verified per adapter, not by the core fixtures; the core fixtures check that untrusted parts reach the adapter with their provenance.

**Readings settled with the Area 7 fixtures**

- CTX-050, CTX-070: context **fits** when its size is at or below the trigger level (`triggerPercent` of the available space), counting any new summary. Compaction removes or summarizes units until it fits or no droppable unit remains. Then, if context exceeds the available space, the run overflows (CTX-090); if it lies between the trigger level and the available space, the call proceeds. With `compaction.mode: none`, only exceeding the available space matters.
- CTX-060: at the model call of step *N*, the **current step** is step *N−1*'s model response with its tool calls and results, which the call answers; earlier steps of the turn are droppable units. The reasoning parts the provider requires are those in that response.
- CTX-010: system content is one `system`-role message with one text part per instruction source: each policy bundle's `policyInstructions` in stack order, then the persona's `instructions`. A principal message keeps its automatically retrieved parts in history. Reasoning parts stay in history and are sent only to the provider that produced them (CORE-142, PROV-055).
- CTX-011: the `content` a `beforeModelCall` hook sees is the parts of the assembled messages, in order, system parts included; `annotate` part indices refer to that list.
- CTX-003: the full content behind a redacted event is referenced by the event's `contentRef`. Retrieved results, summaries and `contentRef` blobs are `application/json`: the part, or the payload content.
- CTX-031: a failing vector store is retried as the profile's `retry.unavailable` allows; if it still fails, the amendment's error handling applies and the turn continues, notwithstanding CORE-191's `fatal` handling of exhausted retries. A vector store query is made with the principal's `{subject, tenant, roles}` (PORT-080 as amended).
- CTX-101: a `retrieval.source` that the deployment's `ports.vectorStore.sources` does not declare is a configuration error, as is a retrieval tool's.
- CTX-080: summarizer calls are provider requests like any other and appear in a scripted provider's recorded requests; they emit no events. On a fallback (CTX-085), the `error` or `policy.decision` precedes `context.compacted`. A folded summary's `provenances` are those recorded for the earlier summary followed by those of the new units, in order of first entry. If the turn budget runs out during summarization (CTX-084), the compaction is not recorded.
- `context.retrieved` carries the turn and `context.compacted` the turn and step of the model call it prepared.

**Further readings settled in review**

- CTX-011, HOOK-091: `annotate` part indices at `beforeModelCall` count the assembled parts in order, system parts included and reasoning parts excluded. Labels a `beforeModelCall` hook adds persist on the parts they label for the rest of the session (labels only grow, HOOK-022); the `hook.decision` records them per part (`annotations`), and later assembly reapplies them (CTX-001). A `beforeModelCall` `rewrite` applies to that model request only; the hooks run again before every call.
- CTX-050, PROV-044, PROV-045: context fits when, for every candidate model, its adapter's count is at or below the trigger level of the available space, where the available space is the smallest `contextLimit` among the candidates minus `reserveOutputTokens`, which defaults to the largest `maxOutputTokens` among them.
- CTX-070: `summarize` chooses the smallest prefix of droppable units (in drop order) whose removal makes the remaining context fit, not counting the summary; it calls the summarizer once; the ordinary fit and overflow rules then apply with the summary counted. If the content compaction may never drop already exceeds the available space, the run overflows (CTX-090) without compacting: no summarizer call and no `context.compacted`.
- CTX-084: if the turn budget runs out during summarization, no `context.compacted` is emitted, and the summarizer's usage is recorded as `unrecordedUsage` on `run.ended`.
- CTX-085: summarizer errors are handled by CTX-085, notwithstanding CORE-191/192: an `unavailable` error is retried as `retry.unavailable` allows; the summarizer has no fallback models; any remaining failure falls back to `truncate`.
- CTX-040, CTX-081: an empty automatic retrieval taints the session (its provenance is recorded in the session's taint provenances, HOOK-126) but adds no part, so it contributes no provenance to the units of its turn or to a summary of them.
