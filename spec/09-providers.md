# Area 9 — Providers

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `domain.md` (approved, incl. providers amendment); notes `providers.md`, `content.md`, `security.md` (settled); ADR-0003, 0005, 0008, 0009, 0013, 0015; Areas 1–7 (approved)

---

## 1. Scope

This area specifies the provider adapter contract, provider declarations, how a model is chosen (the `model` block), model capabilities, sensitivity routing, failover, normalized usage and cost, and how provider errors are mapped.

The `model` block replaces the provisional `model` field (CFG-090, CFG-092) and gives `compaction.model` (CTX-100) and model hooks (HOOK-100) their structure. Schemas for the `model` block, provider declarations, capability declarations, price tables, and normalized usage are specified in Phase 4.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `PROV-`.

## 3. The adapter contract

- **PROV-001** A provider adapter **MUST** translate one harness request into one provider call and translate the response back. It **MUST NOT** loop, and **MUST NOT** execute tool calls; it returns them to the harness (ADR-0003). It **MUST** disable any built-in tool execution of an SDK or framework it wraps.
- **PROV-002** An adapter **MUST** accept: the assembled context (CTX-010), the visible tool definitions (TOOL-020), any output schema (CORE-130), and generation parameters (PROV-022).
- **PROV-003** An adapter **MUST** delimit untrusted content in the provider request (ADR-0008).
- **PROV-004** An adapter **MUST** return the response as content parts (CORE-110): `text`, `tool_call`, `structured`, `reasoning`. Provider-specific data goes in `extensions`.
- **PROV-005** An adapter **MUST NOT** send `reasoning` parts to a provider other than the one that produced them (CORE-142).
- **PROV-006** An adapter **MUST** report normalized usage (§8) for every call, including failed calls where the provider reports usage.
- **PROV-007** An adapter **MUST** map every provider error into the error model (§9).
- **PROV-008** An adapter **MUST** declare the capabilities of each model it serves (§5) and the generation parameters it accepts (PROV-022).
- **PROV-009** The adapter contract and its fixtures apply identically to native adapters and to framework-wrapping adapters such as LangChain (ADR-0013). A framework-wrapping adapter **MUST** be declared against the underlying vendor endpoint it reaches, one provider declaration per vendor endpoint, so routing sees the real destination.

## 4. Providers and the `model` block

### 4.1 Providers

- **PROV-010** Providers **MUST** be declared in the deployment with: an ID, the adapter that serves them, an endpoint, a region, and data-handling attributes (at least `retainsData`). *(Extends CFG-110.)*
- **PROV-011** A model whose provider is not declared is a configuration error.
- **PROV-012** A sensitivity policy allows providers in two ways, both of which must be satisfied: `allowedProviders` (by ID, CFG-070) and an optional `providerRequirement` — a CEL condition (HOOK-110) over the provider's `id`, `region`, and data-handling attributes (e.g. `!provider.retainsData`). A provider's `region` **MUST** also satisfy the policy bundle's `dataResidency` (CFG-070). *(Extends CFG-070.)*
- **PROV-013** Policy checks use the provider declaration as it stands in the effective snapshot, after environment overlays (CFG-021). An overlay that changes a provider's endpoint, region, or attributes is re-evaluated against every policy.

### 4.2 The `model` block

- **PROV-020** Policy bundles, personas, and harness profiles **MAY** declare a `model` block *(extends CFG-070, CFG-080, CFG-090)*:

| Field | Merge rule | Meaning |
|---|---|---|
| `provider` | `locked` | Provider ID |
| `name` | `locked` | Model identifier at that provider |
| `fallbacks` | See PROV-021 | Ordered alternative `{provider, name}` models |
| `params.maxOutputTokens` | `min` | Output token limit, at most the model's `maxOutputTokens` capability |
| `params.<other>` | `override` | Other generation parameters (PROV-022) |

- **PROV-021** `fallbacks` belong to the layer that sets `provider` and `name`. That layer sets the list and its order; lower layers **MAY** only remove entries, and the remaining entries keep their order. A lower layer that adds a fallback is a configuration error.
- **PROV-022** `params` **MUST** contain only generation parameters the adapter declares (PROV-008), such as temperature, top-p, stop sequences, seed, and maximum output tokens. Anything else — including endpoints, regions, tool or safety settings, and data-retention settings — **MUST** be a configuration error. *(Narrows the CFG-033 exemption for the provisional `model` field to these declared generation parameters.)*
- **PROV-023** After merging, every persona **MUST** have a model. The primary model and every fallback **MUST** have a provider in the effective `allowedProviders` (CFG-042). `compaction.model` (CTX-100) and model hooks (HOOK-100) use the same `{provider, name, params}` shape and rule.

## 5. Capabilities

- **PROV-030** Each model's capabilities are declared by its adapter:

| Capability | Type | Meaning |
|---|---|---|
| `contextLimit` | Integer | Maximum input tokens |
| `maxOutputTokens` | Integer | Maximum output tokens; default for `reserveOutputTokens` (CTX-100) |
| `toolUse` | Boolean | Accepts tool definitions and returns tool calls |
| `parallelToolCalls` | Boolean | May return several tool calls in one response |
| `structuredOutput` | Boolean | Supports schema-constrained output natively |
| `vision` | Boolean | Accepts `image` parts |
| `documents` | Boolean | Accepts `file` parts |
| `reasoning` | Boolean | Returns `reasoning` parts |
| `streaming` | Boolean | Can emit deltas |

- **PROV-031** A deployment **MAY** restrict a model's capabilities (lower an integer, turn a boolean off). An attempt to extend a capability **MUST** be a configuration error.

### 5.1 Checks at load time

- **PROV-040** For the primary model **and every fallback**, these mismatches **MUST** be configuration errors:
  - a persona with a non-empty `tools` list, on a model without `toolUse`;
  - a profile with `deliveryMode: streamed`, on a model without `streaming`;
  - an effective `reserveOutputTokens` greater than the model's `maxOutputTokens`.
- **PROV-041** An output schema does not require `structuredOutput`: without it, the harness validates the output itself (CORE-132).

### 5.2 Checks per request

- **PROV-042** `image` parts need `vision` and `file` parts need `documents`.
  - When `run()` is called with attachments that no allowed model for the persona supports, `run()` **MUST** be rejected with `invalid_input` (`agentry.provider.unsupported_content`) before a run starts.
  - When such content enters context during a run (e.g. a tool result), the harness **MUST** use the first capable, allowed fallback (§6). If none exists, the run **MUST** end `failed` with a `fatal` error (`agentry.provider.unsupported_content`).
- **PROV-043** A model without `parallelToolCalls` **MUST** be sent requests that permit at most one tool call per response.
- **PROV-044** The context manager **MUST** compact to the smallest `contextLimit` among the primary model and its remaining fallbacks (CTX-050), so that a routing or failover switch never causes an overflow. *(Clarifies CTX-050.)*

## 6. Sensitivity routing

- **PROV-050** Routing runs after `beforeModelCall` hooks, so it sees every label they add (CTX-011). The model used for the call **MUST** have a provider allowed (PROV-012) by the sensitivity policy of every label on every part in the context being sent.
- **PROV-051** If the current model is not allowed, the harness **MUST** use the first model in `fallbacks` that is allowed for every label and has the capabilities the request needs (PROV-042), and **MUST** emit a `policy.decision` recording the switch. *(Extends the uses of `policy.decision` in CORE-170; these decisions are audited per `domain.md` invariant 14.)*
- **PROV-052** If no model is allowed, the harness **MUST NOT** make the call, **MUST** emit a `policy.decision`, and **MUST** end the run `blocked` with the fallback message (CORE-181). *(Adds a block location to CORE-180.)*
- **PROV-053** Content **MUST NOT** be sent to a provider that is not allowed for every label on it, under any circumstances, including failover (§7), summarization (CTX-080), and model hooks (HOOK-100, HOOK-054).
- **PROV-054** Routing applies per model call; a routing switch does not persist to later steps.
- **PROV-055** When consecutive steps in a turn use different providers, `reasoning` parts produced before the switch **MUST NOT** be sent after it (PROV-005). CTX-060's protection of required reasoning applies only while the same provider continues. *(Clarifies CTX-060.)*

## 7. Failover

- **PROV-060** When a call fails with `unavailable` and the profile's retries (`retry.unavailable`) are used up — immediately, for non-retryable errors such as authentication failure — the harness **MAY** fail over to the next model in `fallbacks` that is allowed (§6) and capable (§5.2).
- **PROV-061** Failover to a model of the **same** provider **MAY** happen at any point.
- **PROV-062** Failover to a **different** provider **MUST** happen only before the first model call of a turn. Mid-turn, if no same-provider fallback is available, the error is treated as `fatal` (CORE-191): the run ends `failed` and the session closes (CORE-020).
- **PROV-063** A failover persists for the rest of the turn; the next turn starts from the primary model.
- **PROV-064** In `streamed` delivery, a call that has already emitted deltas **MUST NOT** be retried or failed over, because delivered text cannot be recalled. Its failure is treated as `fatal`.
- **PROV-065** Every failover **MUST** emit an `error` event for the failed call and record the model used on the next `model.request`.

## 8. Usage and cost

- **PROV-070** Normalized usage **MUST** have `inputTokens` (including cached input), `outputTokens` (including reasoning), `cachedInputTokens`, and `reasoningTokens`. Fields the provider does not report are `0`. Usage is recorded on `model.response` events, and on `error` events for failed calls that reported usage.
- **PROV-071** Token budgets (CFG-091) count `inputTokens + outputTokens` across every model call in the turn, including failed calls and summarization (CTX-084), and excluding model hooks (HOOK-103).
- **PROV-072** The deployment **MAY** declare a price table: per model, prices per million tokens for uncached input, cached input, output, and reasoning output. *(Extends CFG-110.)*
- **PROV-073** If any layer sets `budget.cost`, every model that could run for that persona — primary, fallbacks, summarizer, and model hooks — **MUST** have a price, or configuration is rejected. A run request that sets `budget.cost` (CFG-101) when any such model is unpriced **MUST** be rejected with `invalid_input`.
- **PROV-074** Cost **MUST** be computed from normalized usage and the price table in the session's snapshot. Summarizer cost counts toward `budget.cost`; model hook cost does not (HOOK-103) but **MUST** be recorded on the hook's decision.

## 9. Error mapping

- **PROV-080** Adapters **MUST** map provider errors as follows:

| Provider condition | Category | `retryable` | Code |
|---|---|---|---|
| Rate limit, overload, transient server error, network failure | `unavailable` | `true` | `agentry.provider.unavailable` |
| Authentication or permission failure | `unavailable` | `false` | `agentry.provider.auth` |
| Request rejected as malformed | `fatal` | `false` | `agentry.provider.bad_request` |
| Context length exceeded | `limit` | `false` | `agentry.context.overflow` |
| Safety refusal returned as an error | `policy` | `false` | `agentry.provider.refused` |

- **PROV-081** A safety refusal returned as an error **MUST** end the run `blocked` with the fallback message (CORE-181), source `provider`. A refusal written as ordinary text is a normal response. *(Adds a block location to CORE-180.)*
- **PROV-082** A context-length error **MUST** end the run `context_limit` (CTX-090). Implementations **SHOULD** log it as a defect, since the context manager should have prevented it.
- **PROV-083** Original provider error detail **MAY** be kept in `details`, subject to redaction (CORE-194).

## 10. Recording

- **PROV-090** Every `model.request` event **MUST** record the provider ID, model name, and whether the model is the primary or a fallback, and if a fallback, why: routing, capability, or failover.

## 11. Conformance fixtures (to be written in Phase 4)

All adapter fixtures run against every adapter, native or framework-wrapping.

| Fixture | Requirements |
|---|---|
| Adapter returns tool calls and never executes them; wrapped SDK loop disabled | PROV-001 |
| Request includes context, visible tools, output schema, params | PROV-002 |
| Untrusted content delimited | PROV-003 |
| Response mapped to content parts, including reasoning | PROV-004 |
| Reasoning never sent to another provider | PROV-005, 055 |
| Usage reported, including failed calls; missing fields `0`; cached within input | PROV-006, 070 |
| Capabilities and generation parameters declared per model | PROV-008, 030 |
| Framework-wrapping adapter passes the same fixtures; declared against the real vendor endpoint | PROV-009 |
| Undeclared provider → rejected | PROV-011 |
| Provider fails `providerRequirement` or `dataResidency` → not allowed | PROV-012 |
| Overlay changes provider region → policies re-evaluated | PROV-013 |
| Bundle pins model; persona cannot change it | PROV-020 |
| `maxOutputTokens` tightened only | PROV-020 |
| Lower layer removes a fallback → accepted, order kept; adds one → rejected | PROV-021 |
| Endpoint or undeclared parameter in `params` → rejected | PROV-022 |
| Persona without model; disallowed fallback → rejected | PROV-023 |
| Deployment restricts capability → honoured; extends → rejected | PROV-031 |
| Fallback lacking `toolUse` or `streaming`, or with too small an output limit → rejected | PROV-040 |
| Output schema without native structured output → harness validates | PROV-041 |
| Unsupported attachment at `run()` → `invalid_input`, no run; mid-run → capable fallback or `failed` | PROV-042 |
| Non-parallel model receives single-call requests | PROV-043 |
| Compaction targets the smallest context limit among candidates | PROV-044 |
| Hook adds `phi`; routing sees it and switches; `policy.decision` audited | PROV-050, 051 |
| No allowed model → `blocked`, content never sent | PROV-052, 053 |
| Summarizer or model hook on a disallowed provider never receives content | PROV-053 |
| Routing switch does not persist to the next step | PROV-054 |
| Auth failure → immediate failover eligibility | PROV-060 |
| Same-provider failover mid-turn; cross-provider only at turn start; otherwise `failed`, session closed | PROV-061, 062 |
| Failover persists for the turn; next turn uses primary | PROV-063 |
| Streamed call fails after deltas → no retry, `fatal` | PROV-064 |
| Failover recorded | PROV-065 |
| Token budget counts failed calls and summarizer, excludes hooks | PROV-071 |
| Price table used for cost | PROV-072, 074 |
| `budget.cost` with an unpriced candidate model → rejected at load; via run request → `invalid_input` | PROV-073 |
| Summarizer cost counted; hook cost recorded on its decision | PROV-074 |
| Each provider error mapped per table; detail kept in redacted `details` | PROV-080, 083 |
| Safety refusal error → `blocked` with fallback; textual refusal → normal response | PROV-081 |
| Context-length error → `context_limit` | PROV-082 |
| `model.request` records provider, model, primary/fallback and reason | PROV-090 |

## 12. Additions approved with this spec (2026-10-31)

| ID | Proposed rule |
|---|---|
| PROV-006, 070, 071 | Usage reported and counted for failed calls; cached tokens within input, reasoning within output |
| PROV-009 | Framework-wrapping adapters declared against the real vendor endpoint |
| PROV-010, 011 | Provider declaration contents (extends CFG-110); undeclared provider is an error |
| PROV-012 | **New `providerRequirement` CEL condition** on sensitivity policies over provider attributes; region must satisfy `dataResidency` (extends CFG-070) |
| PROV-013 | Policies evaluated on the effective provider declaration after overlays |
| PROV-020 | `model` block in bundles, personas, profiles (extends CFG-070/080/090); `maxOutputTokens` uses `min` |
| PROV-021 | **Fallbacks owned by the layer that pins the model**; lower layers may only remove |
| PROV-022 | **`params` limited to adapter-declared generation parameters** (narrows the CFG-033 exemption) |
| PROV-023 | Every persona must have a model; summarizer and hook models follow the same rule |
| PROV-030 | Capability list and types |
| PROV-040 | Load-time capability checks apply to fallbacks too |
| PROV-042 | Unsupported attachments rejected at `run()`; mid-run unsupported content is `fatal` |
| PROV-043 | Non-parallel models limited to one tool call per response |
| PROV-044 | **Compaction targets the smallest context limit among candidate models** (clarifies CTX-050) |
| PROV-050 | Routing runs after `beforeModelCall` hooks |
| PROV-051, 052 | Routing decisions are `policy.decision` events (extends CORE-170); no allowed model is a new block location (extends CORE-180) |
| PROV-054 | Routing is per model call |
| PROV-055 | After a provider switch, earlier reasoning isn't sent (clarifies CTX-060) |
| PROV-060 | Failover only after retries; non-retryable `unavailable` (e.g. auth) eligible immediately |
| PROV-062 | Mid-turn outage with no same-provider fallback → run `failed`, session closes |
| PROV-063 | Failover lasts for the rest of the turn |
| PROV-064 | **Streamed calls that have emitted deltas are never retried or failed over** |
| PROV-065 | Failovers recorded with an `error` event |
| PROV-072–074 | Price table (extends CFG-110); run-request cost budgets checked; summarizer cost counts, hook cost recorded |
| PROV-080 | Error mapping table and codes |
| PROV-081 | Provider safety refusal is a new block location (extends CORE-180); textual refusals are normal |
| PROV-082 | Provider context-length errors end the run `context_limit` |
| PROV-090 | `model.request` records which model was used and why |

## Amendment 2026-11-01 — from Phase 4 (Area 7 fixtures)

- **PROV-045** An adapter **MUST** count the tokens of assembled context for its model, deterministically for the same context. The context manager **MUST** use this count for compaction and overflow (CTX-050, CTX-090). The scripted adapter used by the conformance suite counts one token per word of each text part and a fixed cost per other part (`conformance/schema/fixture.yaml`).
