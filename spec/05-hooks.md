# Area 5 — Hooks, guardrails, and the taint rule

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `domain.md` (approved, incl. amendments); notes `hooks.md`, `security.md`, `tools.md`, `content.md` (settled); ADR-0005, 0006, 0007, 0008, 0014, 0015; Areas 1–4 (approved)

---

## 1. Scope

This area specifies the `Hook` artifact, hook points and results, how hooks run and fail, the four hook sources, the agentry CEL subset, the taint rule's decision logic, and how the `policy` approval setting is evaluated.

Run-level outcomes of a block are fixed in Area 1 (CORE-180). Where tool-call hooks and policy checks sit in the tool pipeline is fixed in Area 4 (§6). Escalation handling is specified in Area 6.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `HOOK-`. The schemas `HookDefinition`, `HookRequest`, `HookResult`, and `HookDecision` are specified in Phase 4.

## 3. Hook definition

- **HOOK-001** A `Hook` artifact **MUST** declare `id`, `points`, `results`, `timeoutMs`, and `source`, and **MAY** declare `purpose`, `failureMode`, and `match`:

| Field | Values | Default | Meaning |
|---|---|---|---|
| `points` | One or more hook points (§4) | — | Where the hook runs |
| `results` | Subset of `continue`, `annotate`, `rewrite`, `block`, `escalate` | — | Results the hook may return; `continue` is always implied |
| `purpose` | `guardrail`, `telemetry` | `guardrail` | Governance or observation |
| `failureMode` | `failClosed`, `failOpen` | `failClosed` for guardrails, `failOpen` for telemetry | What an error or timeout means (§6.3) |
| `timeoutMs` | Integer | — | Per-invocation limit |
| `match` | CEL expression (§9) | always | Condition under which the hook runs, e.g. only for certain tools |
| `source` | See §8 | — | How the hook is evaluated |

- **HOOK-002** A hook with `purpose: telemetry` **MUST** declare only `continue` and `annotate`.
- **HOOK-003** A hook **MUST NOT** declare a result that is not permitted at every one of its points (§5). Such a definition is a configuration error.
- **HOOK-004** A hook may sit at several points; it is evaluated separately at each.

## 4. Hook points

| Point | Runs | Sees |
|---|---|---|
| `sessionStart` | Once, before the first turn's first model call | The principal's first input |
| `beforeModelCall` | Before every model call | The assembled request |
| `afterModelCall` | After every model response, before tool dispatch or response handling | The model's output |
| `beforeToolCall` | Tool pipeline stage 6 (Area 4) | The tool call and arguments |
| `afterToolCall` | Tool pipeline stage 10 (Area 4) | The tool result |
| `beforeResponse` | Before a response is released to the principal | The final response (validated against any output schema, CORE-134) |
| `onError` | When an `error` event is emitted | The error |
| `sessionEnd` | When the session closes | Session summary data |

- **HOOK-010** The set of hook points is closed. New points require a spec change.

## 5. Hook results

| Result | Effect |
|---|---|
| `continue` | No change |
| `annotate` | Adds sensitivity labels to parts, or findings, without changing content |
| `rewrite` | Replaces content, subject to Area 1 CORE-126 for binary parts |
| `block` | Stops the action; outcome per CORE-180 |
| `escalate` | Requests a human decision *(Area 6)* |

Results permitted at each point:

| Point | `annotate` | `rewrite` | `block` | `escalate` |
|---|---|---|---|---|
| `sessionStart` | ✓ | ✓ | ✓ | ✓ |
| `beforeModelCall` | ✓ | ✓ | ✓ | ✓ |
| `afterModelCall` | ✓ | ✓ | ✓ | ✓ |
| `beforeToolCall` | ✓ | ✓ (arguments) | ✓ | ✓ |
| `afterToolCall` | ✓ | ✓ (result) | ✓ (withhold) | ✓ |
| `beforeResponse` | ✓ | ✓ | ✓ | ✓ |
| `onError` | ✓ | — | — | — |
| `sessionEnd` | ✓ | — | — | — |

- **HOOK-020** A hook that returns a result it did not declare **MUST** be treated as having failed (§6.3).
- **HOOK-021** A `rewrite` at `beforeToolCall` **MUST** be re-validated per Area 4 TOOL-031. A rewrite cannot raise trust or drop labels: rewritten content **MUST** keep the provenance and at least the labels of the content it replaces, and any part a rewrite inserts **MUST** take the least-trusted provenance and the union of labels of the content being rewritten.
- **HOOK-022** `annotate` **MAY** add labels; it **MUST NOT** remove labels. Every added label **MUST** have a sensitivity policy (ADR-0015).
- **HOOK-023** Every `block` and `escalate` **MUST** carry a reason code, recorded in the hook decision. The reason code **MUST NOT** be shown to the model or the principal: the model receives a generic `policy` error, and the principal receives the fixed fallback message (CORE-181).

## 6. Execution

### 6.1 Order

- **HOOK-030** The hooks at a point **MUST** run in this order: hooks required by each policy bundle in stack order, then the persona's, then the profile's. Within a layer, hooks run in declared order.
- **HOOK-031** A hook runs only if its `match` expression, if any, evaluates to `true`.
- **HOOK-032** `rewrite` results chain: each later hook sees the content as rewritten by earlier ones. `annotate` results accumulate.
- **HOOK-033** The first `block` or `escalate` **MUST** stop the chain; later hooks at that point **MUST NOT** run until the escalation is decided.
- **HOOK-034** When an escalation raised by a hook is approved, the chain **MUST** resume with the next hook at the same point, on the approved content. Required hooks are never skipped by escalation.

### 6.2 Streamed delivery

- **HOOK-040** In a profile with `deliveryMode: streamed`, `beforeResponse` hooks run on the complete response after it has been delivered, and are advisory. Because streamed text cannot be recalled, a profile in which any `afterModelCall` or `beforeResponse` hook declares `rewrite`, `block`, or `escalate` cannot use `streamed`. *(Extends CFG-042, which covered only `block` at output.)*

### 6.3 Failure

- **HOOK-050** A hook that errors, times out, or returns an undeclared or malformed result has **failed**.
- **HOOK-051** A failed `failClosed` hook **MUST** be treated as `block`. A failed `failOpen` hook **MUST** be treated as `continue`. In both cases an `error` event **MUST** be emitted.
- **HOOK-053** `failClosed` applies only to hooks that declare `block` or `escalate`. A hook that declares neither is treated as `continue` when it fails, whatever its failure mode.
- **HOOK-054** A required hook that cannot receive the content it needs — for example, because a sensitivity policy forbids sending it to the hook's endpoint or model — has failed (HOOK-050). It is never silently skipped.
- **HOOK-052** At `onError` and `sessionEnd`, a failed hook is always treated as `continue`, whatever its failure mode, and **MUST NOT** trigger further `onError` hooks.

### 6.4 Recording

- **HOOK-060** Every result other than `continue` **MUST** emit a `hook.decision` event and be written to the audit log, with the hook's `id@version`, point, result, reason code, and snapshot hash.
- **HOOK-061** `continue` results **MUST NOT** emit `hook.decision` events (CORE-170). They **MAY** be recorded in observability spans (Area 11).
- **HOOK-062** A hook decision **MUST** record a hash of the input the hook saw, so evaluation tools can replay decisions or re-evaluate hooks against recorded traffic *(Area 11)*.

## 7. Layering

- **HOOK-070** Hooks are added through `requiredHooks` in policy bundles, personas, and profiles (CFG-070, CFG-080, CFG-090), merged by `union`.
- **HOOK-071** A lower layer **MUST NOT** remove, replace, or re-version a hook required above it (CFG-034). Because failure mode and declared results are part of the versioned hook artifact, they cannot be weakened by a lower layer.

## 8. Hook sources

| `source.kind` | Evaluated by |
|---|---|
| `rule` | The implementation's rule evaluator, from a declarative rule (§9) |
| `native` | A handler registered in the implementation's language |
| `remote` | An external service over HTTP or gRPC |
| `model` | A model acting as a classifier (§8.2) |

- **HOOK-080** At load time every source **MUST** resolve: a rule compiles and type-checks, a `native` handler is registered, a `remote` endpoint is declared in the deployment, a `model` hook's provider is allowed. An unresolved source is a configuration error.
- **HOOK-081** Implementations **MUST** support all four source kinds.

### 8.1 Rule and remote hooks

- **HOOK-090** A rule hook declares `when` (a CEL expression returning a boolean) and `then` (one of `annotate` with labels, `block` with a reason code, or `escalate` with a reason code). If `when` is false, the result is `continue`. Rule hooks **MUST NOT** declare `rewrite`.
- **HOOK-091** A remote hook receives a `HookRequest` (point, tenant, principal reference, session and run IDs, and the content the point sees) and returns a `HookResult`. Credentials come from secret references (CFG-060).
- **HOOK-092** Remote hook endpoints are declared in the deployment. Content sent to a remote hook is subject to the same sensitivity policies as any other processing: a sensitivity policy **MAY** restrict which remote hooks receive content with its label. *(Extends CFG-110.)*

### 8.2 Model-judged hooks

- **HOOK-100** A model hook declares a model, instructions, and a token limit. Its model **MUST** be from an allowed provider (CFG-070, CFG-080) and is subject to the sensitivity policies of the content it sees.
- **HOOK-101** The model's output **MUST** be parsed as a `HookResult`. Anything else is a failure (HOOK-050). A model hook that declares `block` or `escalate` **MUST** be `failClosed`, so injected content that breaks its output cannot turn a block into `continue`.
- **HOOK-102** A model hook **MUST** run with no tools, and its model calls **MUST NOT** pass through hooks or emit `model.request`/`model.response` events. Their token usage **MUST** be recorded on the hook's decision when one is emitted, and **MAY** be recorded in observability spans.
- **HOOK-103** A model hook's tokens count against its own token limit, not the turn budget.
- **HOOK-104** A policy bundle or harness profile **MAY** set `guardrails.requireDeterministic: true` (merge rule `stricter`, order `true` → `false`). Then every point that has a model hook able to `block` **MUST** also have a `rule` or `remote` hook able to `block`; otherwise the configuration is rejected. *(Extends CFG-070 and CFG-090.)*

## 9. The agentry CEL subset

- **HOOK-110** Rule expressions (`when`, `match`, and approval rules) **MUST** use only this subset of CEL (ADR-0006):
  - literals: null, booleans, integers, doubles, strings, lists, maps (JSON-like values only)
  - operators: arithmetic, comparison, logical, `in`, conditional (`? :`), field selection, indexing
  - macros: `has`, `all`, `exists`, `exists_one`, `map`, `filter`
  - standard functions: `size`, `contains`, `startsWith`, `endsWith`, `matches`, and conversions `int`, `double`, `string`, `bool`
  - strings extension: `lowerAscii`, `upperAscii`, `split`, `join`, `replace`, `trim`
- **HOOK-111** Expressions **MUST NOT** use bytes, protobuf message types, custom functions, or timestamp and duration types in 1.0.
- **HOOK-112** Expressions are compiled and type-checked against the variables available at their point (§9.1) at load time. Failure is a configuration error.
- **HOOK-113** Evaluation errors at run time (for example, a missing map key) **MUST** be treated as a hook failure (HOOK-050).
- **HOOK-114** `matches` uses RE2 syntax.

### 9.1 Variables

| Variable | Available at | Contents |
|---|---|---|
| `principal` | All points | `subject`, `tenant`, `roles`, `attributes`, `assurance` |
| `session` | All points | `persona`, `tainted`, `turn`, `step` |
| `content` | Points that see content | List of parts: `type`, `text` (text parts), `labels`, `provenance` |
| `tool` | `beforeToolCall`, `afterToolCall` | `id`, `effect`, `egress`, `idempotent`, `sensitivity` |
| `call` | `beforeToolCall` | `arguments` |
| `result` | `afterToolCall` | `ok`, `output` or `error` |
| `error` | `onError` | `code`, `category`, `source` |

- **HOOK-115** Variables **MUST NOT** expose secret values, credentials, or binary content.

Per ADR-0006, each implementation evaluates rules behind a replaceable rule evaluator, so a CEL library can be swapped without changing behaviour.

## 10. The taint rule

The taint rule is a deterministic policy check in the harness. It is not a hook and cannot be removed by configuration.

- **HOOK-120** A session becomes **tainted** when content that is not trusted enters the model's context: tool results not listed in `trustedTools`, attachments from sources not listed in `trustedAttachmentSources`, retrieved content, and delegated-session output that is itself untrusted (ADR-0008).
- **HOOK-121** Taint is sticky: once tainted, a session remains tainted until it closes, including across compaction, checkpoint, and resume (ADR-0008).
- **HOOK-126** The session **MUST** record the provenance of the content that first tainted it, and every later untrusted provenance that entered context. Each taint `policy.decision` **MUST** include them, so audits show what influenced the action.
- **HOOK-122** At tool pipeline stage 5 (Area 4), for a tainted session, two conditions are checked:
  - **mutating condition** — the tool is `mutating` → outcome: effective `onTainted`;
  - **egress condition** — the tool is `egress` **and** any part in context carries a sensitivity label → outcome: effective `onTaintedEgress`.

  If both conditions hold, the stricter outcome applies; if one holds, its outcome applies; if neither holds, the call continues.
- **HOOK-123** Effective outcomes are the stricter of the tool's own setting and any policy-bundle `toolTaintDefaults` entry (CFG-042, TOOL-003).
- **HOOK-124** Every taint-rule evaluation in a tainted session where at least one condition holds — including an outcome of `allow` — **MUST** emit a `policy.decision` event and an audit record.
- **HOOK-125** The taint rule **MUST** be evaluated before `beforeToolCall` hooks, and hooks **MUST NOT** be able to override its outcome.

## 11. Approval policy

- **HOOK-130** Policy bundles and personas **MAY** declare `approvalRules`: CEL expressions (§9) evaluated at tool pipeline stage 7 with the `beforeToolCall` variables. Merge rule: `union`. *(Extends CFG-070 and CFG-080.)*
- **HOOK-131** For a call whose effective approval is `policy` (TOOL-035), the call **MUST** escalate if any approval rule evaluates to `true`, and continue otherwise. If no approval rules are declared at all, the call **MUST** escalate.
- **HOOK-132** An approval rule evaluation error **MUST** be treated as `true` (escalate).

## 12. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Hook missing a required field → rejected | HOOK-001 |
| Telemetry hook declaring `block` → rejected | HOOK-002 |
| Hook at `onError` declaring `rewrite` → rejected | HOOK-003 |
| Default failure modes by purpose | HOOK-001 |
| Undeclared result returned → failure → fail-closed block | HOOK-020, 050, 051 |
| `rewrite` keeps provenance; tool-argument rewrite re-validated | HOOK-021 |
| `annotate` adds a label; removal attempt rejected; unmapped label rejected | HOOK-022 |
| Block reason recorded; never shown to model or principal | HOOK-023 |
| Policy-bundle hooks run before persona and profile hooks | HOOK-030 |
| `match` false → hook skipped | HOOK-031 |
| Chained rewrites apply in order; annotations accumulate | HOOK-032 |
| First block stops later hooks | HOOK-033 |
| Streamed profile: advisory `beforeResponse` hook runs after delivery | HOOK-040 |
| Guardrail timeout → block; telemetry error → continue; both emit `error` | HOOK-051 |
| Failing `onError` hook → continue, no recursion | HOOK-052 |
| Non-continue result → `hook.decision` + audit; continue → no event | HOOK-060, 061 |
| Hook decision includes input hash | HOOK-062 |
| Lower layer re-versions a required hook → rejected | HOOK-071 |
| Unresolved source of each kind → rejected | HOOK-080 |
| Rule hook: `when` true → `then` result; false → continue | HOOK-090 |
| Remote hook request contents; credentials by secret reference | HOOK-091 |
| Sensitivity policy prevents labelled content reaching a remote hook | HOOK-092 |
| Model hook output not a valid `HookResult` → failure | HOOK-101 |
| Model hook calls bypass hooks, emit no model events; no tools; usage on decision | HOOK-102 |
| Model hook tokens not counted toward turn budget | HOOK-103 |
| `requireDeterministic` with only a model block hook, or only a native one → rejected | HOOK-104 |
| CEL outside subset → rejected; type error → rejected | HOOK-110–112 |
| CEL runtime error → hook failure | HOOK-113 |
| CEL edge cases: integer division, null and missing fields, RE2 `matches` | HOOK-110, 114 |
| Variables contain no secrets or binary content | HOOK-115 |
| Untrusted tool result, attachment, or retrieval → session tainted; remains tainted | HOOK-120, 121 |
| Trusted tool result → no taint | HOOK-120 |
| Tainted + mutating → escalate by default | HOOK-122 |
| Tainted + egress + labelled content → block by default | HOOK-122 |
| Tainted + egress, no labelled content → continue | HOOK-122 |
| Mutating + egress → stricter outcome | HOOK-122 |
| Bundle default stricter than tool setting → bundle applies | HOOK-123 |
| Taint decision → `policy.decision` + audit | HOOK-124 |
| Hook cannot override a taint block | HOOK-125 |
| Approval rule true → escalate; false → continue; error → escalate; no rules declared → escalate | HOOK-130–132 |
| Unknown hook point in a definition → rejected | HOOK-010 |
| One hook at two points evaluated at each | HOOK-004 |
| Rewrite cannot drop labels; inserted part is least-trusted | HOOK-021 |
| Hook escalation approved → chain resumes at the next hook | HOOK-033, 034 |
| Streamed profile with blocking/rewriting `afterModelCall` or `beforeResponse` hook → rejected at load | HOOK-040 |
| Annotate-only `failClosed` hook fails → continue | HOOK-053 |
| Required remote hook barred by sensitivity policy → failure, fail-closed block | HOOK-054 |
| Persona tries to remove a bundle hook → rejected | HOOK-070, 071 |
| Implementation supports all four source kinds | HOOK-081 |
| Model hook from a disallowed provider → rejected | HOOK-100 |
| Model hook declaring `block` with `failOpen` → rejected | HOOK-101 |
| CEL: each operator and macro behaves identically | HOOK-110 |
| `annotate` adds `phi` → sensitivity policy for `phi` applies | HOOK-022 (with ADR-0015) |
| Replay: recorded decisions reused; re-evaluation runs hooks again | HOOK-062 (with Area 11) |
| Taint survives compaction, checkpoint, and resume | HOOK-121 |
| Taint decision lists the tainting provenances | HOOK-126 |
| Tainted mutating call with `onTainted: allow` → audited | HOOK-124 |

## 13. Additions approved with this spec (2026-10-31)

| ID | Proposed rule |
|---|---|
| HOOK-001, 004 | Hook fields `purpose` and `match`; `timeoutMs` required; failure-mode defaults by purpose; one hook may sit at several points |
| HOOK-002 | Telemetry hooks may only `continue` or `annotate` |
| HOOK-021 | A rewrite cannot raise trust or drop labels; inserted parts are least-trusted |
| HOOK-022 | `annotate` can add labels but never remove them |
| HOOK-023 | Block and escalate carry a reason code, never shown to the model or principal |
| HOOK-034 | After an approved hook escalation, the chain resumes at the next hook |
| HOOK-030 | Hook order across layers: bundles, then persona, then profile |
| HOOK-040 | **Streamed mode is rejected if any `afterModelCall` or `beforeResponse` hook can rewrite, block, or escalate** (extends CFG-042) |
| HOOK-051 | A failed hook emits an `error` event |
| HOOK-053 | Fail-closed applies only to hooks that can block or escalate |
| HOOK-054 | A required hook barred from its content by sensitivity policy counts as failed |
| HOOK-052 | Failures at `onError`/`sessionEnd` never block and never recurse |
| HOOK-062 | Decisions record an input hash for replay |
| HOOK-091 | Contents of a remote `HookRequest` |
| HOOK-101 | **Model hooks that can block must fail closed** |
| HOOK-102 | Model hook calls emit no model events; usage recorded on the decision |
| HOOK-081 | All four source kinds mandatory for implementations |
| HOOK-090 | Rule hooks use `when`/`then` and cannot rewrite |
| HOOK-092 | Remote hook endpoints declared in the deployment; sensitivity policies may restrict them (extends CFG-110) |
| HOOK-103 | **Model-judged hooks have their own token limit and do not consume the turn budget** |
| HOOK-104 | `guardrails.requireDeterministic` in bundles and profiles; deterministic means `rule` or `remote` (extends CFG-070, CFG-090) |
| HOOK-110–114 | The exact CEL subset and function list; RE2 regex; no bytes, timestamps, or durations; runtime evaluation errors count as hook failures |
| §9.1 | The set of CEL variables per point, including `session.tainted` |
| HOOK-115 | CEL variables never expose secrets or binary content |
| HOOK-120 | Exact sources that taint a session |
| HOOK-122 | **"Sensitive content in context" means any part carrying any sensitivity label** |
| HOOK-124 | Taint decisions audited even when the outcome is `allow` |
| HOOK-125 | Hooks cannot override the taint rule |
| HOOK-126 | Sessions record which provenances tainted them |
| HOOK-130–132 | **New `approvalRules` field** for `approval: policy`; evaluation errors escalate; with no rules declared, `policy` escalates (extends CFG-070, CFG-080) |

## Amendment 2026-10-31 — from Area 10

- HOOK-061, HOOK-102: observability spans are produced through the optional telemetry exporter (PORT-100–102), never a system of record.

## Amendment 2026-10-31 — from Area 11

- HOOK-062: hook input hashes are computed over content canonicalized with RFC 8785 (EVAL-000). In replay-decisions mode, hooks without a recorded decision are re-evaluated and divergences reported (EVAL-063).

