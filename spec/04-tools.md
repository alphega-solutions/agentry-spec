# Area 4 — Tools

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `domain.md` (approved, incl. amendments); notes `tools.md` (incl. amendment), `security.md`, `content.md` (settled); ADR-0003, 0008, 0009, 0013, 0014, 0015; Areas 1–3 (approved)

---

## 1. Scope

This area specifies the `Tool` artifact, where tools come from (bindings), which tools the model can see (scoping), how a tool call is processed and executed, and the rules for importing tools from MCP servers.

Specified elsewhere: the taint rule's decision logic and hooks (Area 5), escalation and decisions (Area 6), delegation depth and nested-session details (Area 8), storage ports (Area 10).

Where this spec and `notes/tools.md` differ, this spec governs. In particular, a call outside the runtime scope produces a `policy` error (Area 1, CORE-180), not `unauthorized` as the note suggested.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `TOOL-`. Schemas `ToolDefinition`, `ToolResult`, and `ToolContext` are specified in Phase 4.

## 3. Tool definition

A `Tool` artifact (Areas 2–3, CFG-001) holds one tool definition: the language-neutral description that governance acts on.

- **TOOL-001** A tool definition **MUST** declare `id`, `description`, `input`, `effect`, and `binding`, and **MAY** declare the other fields below:

| Field | Values | Default | Meaning |
|---|---|---|---|
| `description` | Text | — | Shown to the model |
| `input` | JSON Schema | — | Arguments; its top level **MUST** be an object |
| `output` | JSON Schema | none | Expected `ok` output |
| `effect` | `read`, `mutating` | — | Whether the tool changes state |
| `egress` | Boolean | `false` | Whether the tool sends data outside the trust boundary (ADR-0008) |
| `idempotent` | Boolean | `false` | Whether repeating a call with the same idempotency key is safe |
| `approval` | `never`, `policy`, `always` | `never` | When human approval is required *(Area 6)* |
| `sensitivity` | Label set | empty | Labels applied to the tool's results (ADR-0015) |
| `credentialMode` | `principal`, `service` | `principal` | Whose credentials the binding uses (ADR-0014) |
| `minAssurance` | Assurance level (§3.1) | none | Minimum principal assurance to call the tool |
| `onTainted` | `escalate`, `block`, `allow` | `escalate` | Taint outcome for a mutating call *(Area 5)* |
| `onTaintedEgress` | `block`, `escalate` | `block` | Taint outcome for an egress call with sensitive content in context *(Area 5)* |
| `timeoutMs` | Integer | profile `timeouts.tool` | Per-call timeout |
| `binding` | See §4 | — | How the tool is invoked |

- **TOOL-002** `id` **MUST** match `^[a-zA-Z0-9_-]{1,64}$`, so it is accepted by every supported provider's tool-naming rules.
- **TOOL-003** A tool that is both mutating and egress is subject to both taint outcomes; the stricter applies. Effective outcomes combine with policy-bundle `toolTaintDefaults` as specified in CFG-042.
- **TOOL-004** `trustedOutput` **MUST NOT** appear in a tool definition. Output trust is granted only through a policy bundle's `trustedTools` (CFG-070, CFG-071).

Label-to-policy completeness is validated at load time under CFG-042.

### 3.1 Assurance levels

- **TOOL-005** Assurance levels are, from weakest to strongest: `none`, `single_factor`, `multi_factor`, `phishing_resistant`. The host sets the principal's level; a principal meets `minAssurance` if its level is equal or stronger.

## 4. Bindings

| `binding.kind` | Invokes | Notes |
|---|---|---|
| `native` | A handler registered in the implementation's language | For in-process tools |
| `mcp` | A tool on an MCP server | Primary path for reusing one tool across all implementations (§8) |
| `http` | An HTTP endpoint, declaratively mapped (e.g. from an OpenAPI operation) | No code |
| `agent` | Another persona, as a nested session | Delegation (§9) |
| `langchain` | A LangChain tool, through the optional adapter | ADR-0013 |

- **TOOL-010** At load time, every binding **MUST** resolve: a `native` handler is registered, an `mcp` server is declared in the deployment and advertises the tool with a compatible input schema (§8), an `http` endpoint is declared, an `agent` binding references a persona in the snapshot. An unresolved binding is a configuration error.
- **TOOL-011** Credentials used by a binding **MUST** come from secret references (CFG-060) and **MUST NOT** enter model context, events, or traces.
- **TOOL-012** A binding with `credentialMode: principal` **MUST** obtain credentials for the session's principal. A binding with `credentialMode: service` uses a shared credential and **MUST** itself enforce the principal's rights before acting.
- **TOOL-013** Implementations **MUST** support `native`, `mcp`, `http`, and `agent` bindings. `langchain` is optional.

## 5. Scoping

- **TOOL-020** The tools visible to the model for a step **MUST** be exactly: tool catalog ∩ persona `tools` allowlist ∩ runtime scope.
- **TOOL-021** The **runtime scope** is supplied by the host with each run request, as a set of tool references derived from its authorization of the principal. If the host supplies none, the runtime scope equals the persona's allowlist.
- **TOOL-022** A delegated session's visible tools **MUST** be the intersection of its own persona's allowlist and the caller's runtime scope (ADR-0014).
- **TOOL-023** The model **MUST NOT** be told about tools outside its visible set, including through error responses (see stage 1 below).

## 6. The tool call pipeline

Every tool call the model requests passes through these stages, in order. A stage that stops the call produces a tool result error for the model (Area 1, CORE-180) unless stated otherwise.

| # | Stage | Stops the call with |
|---|---|---|
| 1 | **Availability check** — the tool exists and is in the visible set | `policy` (`agentry.tool.unavailable`), identical whether the tool is unknown or out of scope; a `policy.decision` event records which |
| 2 | **Argument validation** against `input` | `invalid_input` (`agentry.tool.invalid_arguments`) |
| 3 | **Idempotency check** (§7.3) — if the call's key has a recorded outcome | Recorded outcome returned; stages 4–9 skipped |
| 4 | **Assurance check** against `minAssurance` | `policy` (`agentry.tool.assurance`); `policy.decision` event |
| 5 | **Taint rule** *(Area 5)* | `policy`, or escalation; `policy.decision` event |
| 6 | **`beforeToolCall` hooks** *(Area 5)* | `policy`, escalation, or rewritten arguments (re-validated per stage 2) |
| 7 | **Approval** — effective approval (TOOL-035): `always` escalates; `policy` defers to Area 5 rules; `never` continues | Escalation *(Area 6)* |
| 8 | **Dispatch** with tool context and timeout (§7.1–7.2) | Per §7.2 |
| 9 | **Result checks** — output validation, provenance, labels (§7.4) | Per §7.4 |
| 10 | **`afterToolCall` hooks** *(Area 5)* | Withheld result → `policy` error |
| 11 | **Recording** — size handling (§7.4), then `tool.result` | — |
| 12 | **Delivery** of the result to the model | — |

- **TOOL-030** Implementations **MUST** apply the stages in this order. A call stopped at a stage **MUST NOT** reach later stages.
- **TOOL-031** Arguments rewritten by a `beforeToolCall` hook **MUST** be re-validated against `input` before continuing.
- **TOOL-032** Parallel calls from one model response (one step, CORE-081) **MUST** each pass through the pipeline independently. Results **MUST** be delivered to the model together, in the order the calls were requested.
- **TOOL-033** If any call in a step escalates, the other calls in the step **MUST** still be processed to completion and their results recorded. All results, including the escalated call's, are delivered together after the escalation is decided.
- **TOOL-034** Every dispatched call **MUST** emit `tool.call` before dispatch. Every call **MUST** produce exactly one `tool.result` event, emitted at stage 11 for dispatched calls and at the stopping stage for stopped calls. *(This clarifies CORE-170: `tool.result` also records results the harness produces.)*
- **TOOL-035** The effective approval for a call is the strictest of the tool's `approval` and the approval set by the sensitivity policies of the tool's labels (ADR-0015, CFG-070).
- **TOOL-036** When a call resumes after an escalation, processing continues at the stage after the one that escalated. The arguments a human approved **MUST** be dispatched unchanged; if a later stage would rewrite them, the call **MUST** escalate again with the rewritten arguments.

## 7. Execution

### 7.1 Tool context

- **TOOL-040** Every dispatched call **MUST** receive a tool context containing: session ID, run ID, principal, idempotency key, deadline, cancellation signal, and trace context.
- **TOOL-041** The idempotency key **MUST** be stable for a given call across retries and resumes, and unique across calls.

### 7.2 Errors, timeouts, and retries

- **TOOL-050** A tool returns either `ok` with output or an error in the Area 1 error shape (CORE-190).
- **TOOL-051** A call exceeding its timeout **MUST** be cancelled and produce `unavailable` (`agentry.tool.timeout`, `retryable: true`).
- **TOOL-052** The implementation **MAY** retry an error marked `retryable`, up to the profile's `retry.unavailable`, **only** if the tool's `effect` is `read` or the tool is `idempotent`.
- **TOOL-053** When retries are exhausted, or a retryable error occurs on a call that may not be retried, the error is treated as `fatal` (CORE-191): the run ends `failed`.
- **TOOL-054** Errors returned to the model **MUST** carry only the safe `message`, `code`, and category; `details` are subject to redaction (CORE-190).

### 7.3 Idempotency

- **TOOL-060** For every mutating call, the implementation **MUST** record in the idempotency store, before dispatch, that the call has started, and after completion, its outcome. The idempotency store is tenant-scoped (ADR-0014).
- **TOOL-061** A call whose idempotency key has a recorded outcome **MUST NOT** be dispatched again; the recorded outcome is returned (`domain.md` invariant 8).
- **TOOL-062** A mutating call recorded as started but with no recorded outcome (for example, after a crash) **MUST**:
  - be re-dispatched with the same idempotency key, if the tool is `idempotent`; otherwise
  - not be re-dispatched, and instead escalate so a human can confirm the outcome.

### 7.4 Result handling

- **TOOL-070** If the tool declares `output` and an `ok` result does not validate, the result **MUST** be replaced by a `fatal` error (`agentry.tool.invalid_output`, source `harness`). The run ends `failed`, which closes the session (CORE-020).
- **TOOL-071** Every result **MUST** carry provenance `tool:<id>` and the tool's sensitivity labels. It is untrusted unless the effective policy lists the tool in `trustedTools` (CFG-070).
- **TOOL-072** After `afterToolCall` hooks, a result larger than the implementation's inline limit **MUST** be stored in the BlobStore and passed to the model as a blob reference (CORE-154). A result larger than the profile's `limits.partSize` **MUST** instead be replaced by an error `limit` (`agentry.tool.result_too_large`) (CORE-115, CORE-191).
- **TOOL-073** Events and blobs **MUST** record the result as it stands after `afterToolCall` hooks. A withheld result is recorded only as its `policy` error.
- **TOOL-074** Every mutating call and its outcome **MUST** be written to the audit log with the snapshot hash (`domain.md` invariant 14).

### 7.5 Cancellation

- **TOOL-080** When a run is cancelled, in-flight calls **MUST** receive the cancellation signal, and their outcomes, if any, **MUST** be recorded (CORE-072).

## 8. MCP tools

- **TOOL-090** Every MCP tool used by a persona **MUST** have its own `Tool` artifact. Implementations **MUST NOT** expose MCP tools to the model directly from server discovery.
- **TOOL-091** The `Tool` artifact, not the MCP server, sets `effect`, `egress`, `idempotent`, `approval`, `sensitivity`, `credentialMode`, `minAssurance`, `onTainted`, and `onTaintedEgress`. MCP tool annotations (read-only, destructive, idempotent, open-world hints) **MUST NOT** influence governance.
- **TOOL-092** The server's advertised input schema **MUST** be compatible with the artifact's `input`:
  - at load time, incompatibility is a configuration error (TOOL-010);
  - if a server changes while sessions run, calls to the affected tool **MUST** fail with `unavailable` (`agentry.tool.schema_drift`, `retryable: false`), recorded as that call's `tool.result`.
- **TOOL-093** MCP servers are declared in the deployment by endpoint and identity. A tool **MUST NOT** bind to an undeclared server. *(Extends CFG-110's list of deployment contents.)*
- **TOOL-094** Content returned by an MCP tool is a tool result like any other: provenance `tool:<id>`, untrusted by default.

Tooling that generates `Tool` artifacts from an MCP server's tool list is encouraged, but its output is configuration that a person reviews.

## 9. Delegation (`agent` binding)

- **TOOL-100** An `agent` binding invokes the referenced persona as a nested session with the caller's principal and tenant.
- **TOOL-101** The nested session's visible tools **MUST** follow TOOL-022.
- **TOOL-102** The nested session's output **MUST** be returned to the caller as a tool result with provenance `agent:<persona>`, carrying the most untrusted provenance the nested session saw (ADR-0008) and the union of the sensitivity labels it saw.
- **TOOL-103** Budgets, depth limits, and escalation inside nested sessions are specified in Area 8.

## 10. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Tool missing a required field; non-object `input` → rejected | TOOL-001 |
| Invalid tool `id` → rejected | TOOL-002 |
| Mutating + egress tool: stricter taint outcome applies | TOOL-003 |
| `trustedOutput` in a tool definition → rejected | TOOL-004 |
| Principal level vs `minAssurance` ordering | TOOL-005 |
| Unresolved binding of each kind → rejected | TOOL-010 |
| Credentials absent from model context, events, traces | TOOL-011 |
| `principal` mode uses principal's credential; `service` binding refuses an unauthorized principal | TOOL-012 |
| Implementation supports the four mandatory bindings | TOOL-013 |
| Visible set = catalog ∩ allowlist ∩ runtime scope; default scope = allowlist | TOOL-020, 021 |
| Delegated scope = own allowlist ∩ caller's runtime scope | TOOL-022, 101 |
| Unknown and out-of-scope tools give identical model-facing errors | TOOL-023, stage 1 |
| Invalid arguments → `invalid_input`; model corrects | Stage 2 |
| Completed mutating call on resume → recorded outcome, no governance re-run, no dispatch | Stage 3, TOOL-061 |
| Principal below `minAssurance` → `policy` | Stage 4 |
| Untainted turn → normal approval policy applies | Stages 5, 7 |
| Hook rewrites arguments → re-validated | Stage 6, TOOL-031 |
| `approval: always` → escalation; approved → dispatched unchanged | Stage 7, TOOL-036 |
| Stage failure stops later stages (e.g. no hooks after availability failure) | TOOL-030 |
| Parallel calls processed independently; delivered together in request order | TOOL-032 |
| One parallel call escalates; others complete; all delivered after decision | TOOL-033 |
| Exactly one `tool.result` per call; `tool.call` only for dispatched calls | TOOL-034 |
| Label policy requiring approval raises effective approval | TOOL-035 |
| Rewrite after approval → re-escalation | TOOL-036 |
| Tool context contents; idempotency key stable across retry and resume | TOOL-040, 041 |
| Timeout → `unavailable`, `agentry.tool.timeout` | TOOL-051 |
| Retry for read or idempotent tool; none for non-idempotent mutating tool | TOOL-052 |
| Retries exhausted → run `failed` | TOOL-053 |
| Model-facing error excludes `details` | TOOL-054 |
| Started/outcome records written; store tenant-scoped | TOOL-060 |
| Crash mid-call: idempotent → re-dispatched with same key; non-idempotent → escalates | TOOL-062 |
| Output failing `output` schema → run `failed`, `agentry.tool.invalid_output` | TOOL-070 |
| Result provenance and labels; trusted only via `trustedTools` | TOOL-071 |
| Result above inline limit → blob reference; above `partSize` → `limit` | TOOL-072 |
| Hook-redacted result is what events record; withheld result recorded as error | TOOL-073 |
| Labels visible to `afterToolCall` hook and tracer | TOOL-071, 073 |
| Conflicting provider allowlists across labels → intersection | TOOL-035 (with ADR-0015) |
| Mutating call audited with snapshot hash | TOOL-074 |
| Cancel during call → tool receives signal, outcome recorded | TOOL-080 |
| MCP tool without `Tool` artifact → not offered | TOOL-090 |
| MCP hint contradicts artifact → artifact governs | TOOL-091 |
| MCP schema incompatible at load → rejected; drift at runtime → `agentry.tool.schema_drift` | TOOL-092 |
| Binding to undeclared MCP server → rejected | TOOL-093 |
| MCP result untrusted by default | TOOL-094 |
| Delegated session output provenance and labels | TOOL-100, 102 |

## 11. Additions approved with this spec (2026-10-31)

| ID | Proposed rule |
|---|---|
| TOOL-001 | Field defaults; `input` must be an object schema; **taint split into `onTainted` (mutating, default `escalate`) and `onTaintedEgress` (default `block`, never `allow`)** |
| TOOL-002 | Tool `id` pattern for provider compatibility |
| TOOL-005 | Four well-known assurance levels and their order |
| TOOL-013 | `native`, `mcp`, `http`, `agent` mandatory for implementations; `langchain` optional |
| TOOL-021 | Host supplies runtime scope per run request; absent means the persona allowlist |
| TOOL-023 / stage 1 | Unknown and out-of-scope tools return the same error, so hidden tools can't be detected |
| TOOL-030 | The 12-stage pipeline and its order. **Idempotency check runs before governance** (a completed action isn't re-governed); **approval runs after hooks**, so humans approve final arguments |
| TOOL-032, 033 | Results delivered together in request order; on escalation, other calls complete first |
| TOOL-034 | Exactly one `tool.result` per call, including calls the harness stops (clarifies CORE-170) |
| TOOL-035 | Effective approval = strictest of tool and label policies |
| TOOL-036 | On resume, approved arguments are dispatched unchanged; a later rewrite re-escalates |
| TOOL-040, 041 | Run ID in the tool context; idempotency key unique across calls |
| TOOL-051 | Timeout is `unavailable` and retryable |
| TOOL-060 | "Started" record written before dispatch |
| TOOL-062 | **Unknown outcome of a non-idempotent mutating call escalates to a human** |
| TOOL-070 | **Invalid tool output is `fatal`**: the run fails and the session closes. Alternative: return it to the model as an error and continue |
| TOOL-072 | Result above `partSize` is replaced by a `limit` error (ends the run) |
| TOOL-073 | Events record results after `afterToolCall` hooks, never raw |
| TOOL-090 | Every MCP tool needs its own reviewed `Tool` artifact |
| TOOL-092 | MCP schema checked at load; runtime drift fails the call |
| TOOL-093 | MCP servers declared in the deployment (extends CFG-110) |
| TOOL-102 | Delegated output carries the union of labels the nested session saw |

## Amendment 2026-10-31 — from Area 7

- §4 bindings gain `retrieval`: queries a vector store source. Retrieval tools must have `effect: read`; their results carry provenance `retrieval:<source>` and can never be trusted (CTX-020, CTX-021).

## Amendment 2026-10-31 — from Area 8

- TOOL-022: a child's visible tools are its allowlist ∩ the parent's **visible** tools, not the parent's runtime scope (ORCH-013).
- TOOL-032: agent-bound calls in one step run one at a time, in request order (ORCH-040).
- TOOL-051: time spent `suspended` does not count toward tool deadlines (ORCH-044).
- TOOL-053 / TOOL-062: agent-bound tools always record a started record holding the child session ID and are idempotent by construction (ORCH-002); their error results never end the parent run by themselves (ORCH-051).

## Amendment 2026-11-01 — from Phase 4 (Area 4 schemas)

- **TOOL-010, `http` bindings**: a binding names an `endpoint` and an `operation`. Deployments declare `httpEndpoints`, each with a base URL and the operations tools may call (method and path template); an undeclared endpoint or operation is a configuration error. *(Extends CFG-110.)*
- **Binding fields** are normative in `schemas/config/v1/tool.yaml`: `native.handler`, `mcp.server` and `mcp.tool`, `http.endpoint` and `http.operation`, `agent.persona`, `retrieval.source`, `langchain.tool`, and an optional `credentials` map of secret references on every binding.
- **TOOL-072, oversized results**: a result larger than `limits.partSize` is replaced by a `limit` error (`agentry.tool.result_too_large`) and the run ends `context_limit` (session → `idle`), the end reason for content that cannot be carried (CORE-191 "matching reason").
- **TOOL-030 stage 1**: the `policy.decision` for an unavailable tool records `reason`: `unknown` (not in the catalog), `out_of_scope` (outside the persona allowlist or runtime scope), or `delegation` (hidden only because a delegated session is limited to its caller's visible tools, ORCH-013). The model-facing error is identical in every case (TOOL-023).
- **TOOL-035**: the label-driven approval uses the labels declared on the **tool** (`sensitivity`), as TOOL-035 states; it does not depend on what else is in context.
- **TOOL-030 stage 1 precedence**: `unknown` takes precedence over `out_of_scope`, which takes precedence over `delegation`.
- **TOOL-036 with hooks**: when an escalation was raised by a `beforeToolCall` hook, processing resumes within stage 6 at the next hook (HOOK-034), then continues to stage 7. Escalations raised at stages 5 or 7 resume at the next stage.
- **TOOL-053 and non-retryable errors**: a tool error with `retryable: false` is delivered to the model as the call's result, whatever its category, except `fatal` (ends the run `failed`) and `cancelled`. Only a retryable error that may not be retried (TOOL-052) or has exhausted its retries is treated as `fatal`. This makes ORCH-051 and HITL's confirmed failures consistent without exceptions. *(Amends CORE-191's `unavailable` row for tool errors.)*
- **TOOL-072 with other calls in the step**: an oversized result ends the run as soon as it is detected; calls in the same step that have not yet been dispatched are not dispatched, and no escalation is raised for them.
- **TOOL-073, where raw outcomes live**: the idempotency store keeps the raw outcome (it is tenant-scoped and encrypted at rest, PORT-002, PORT-006), so a recovered call can be processed through stage 10. Events, the blobs they reference, and audit records (TOOL-074) hold only the outcome as it stands after `afterToolCall` hooks.
- **TOOL-092, compatibility**: the server's advertised input schema is compatible when every property the artifact's `input` declares exists in the server schema with the same JSON type, and the server requires no property the artifact does not require. Implementations **MUST** re-check compatibility on the server's tools-changed notification and on reconnect, before the next call.
- **Binding credentials**: `credentials` is allowed on `native` and `langchain` bindings only. `mcp` and `http` bindings use the credentials on their deployment server or endpoint; `agent` and `retrieval` bindings take none. With `credentialMode: principal`, the references are resolved per principal (CFG-062).
- **Agent tools** are idempotent by construction (ORCH-002); declaring `idempotent: false` on an `agent`-bound tool is a configuration error.

