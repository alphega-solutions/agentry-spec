# Design notes — Hooks and guardrails

**Status:** Settled 2026-10-31 (non-normative working notes) · **Date:** 2026-10-31
**Feeds:** Phase 1 (`domain.md` concepts) and Phase 3 (Area 5 — Hooks and guardrails spec)
**Related:** `notes/tools.md` (sensitivity labels and policies)

> These notes capture agreed direction. Nothing here is binding until it appears in `domain.md`, the Area 5 spec, and conformance fixtures.

---

## 1. Terms

- **Hook** — the mechanism: a typed extension point in the harness loop that returns a decision.
- **Guardrail** — a hook with a governance purpose (safety, privacy, policy). Same machinery, stricter defaults.
- **Guardrail pipeline** — an ordered set of guardrails, declared in configuration.

Telemetry and metrics hooks use the same machinery without being guardrails.

## 2. Hook points

A small, fixed set:

| Hook point | Typical use |
|---|---|
| `sessionStart` | Input guardrails on the initial request |
| `beforeModelCall` | Input guardrails, context checks |
| `afterModelCall` | Inspect model output before tool dispatch |
| `beforeToolCall` | Tool guardrails, approval policy |
| `afterToolCall` | Redaction and labelling of tool results |
| `beforeResponse` | Output guardrails |
| `onError` | Error handling, alerting |
| `sessionEnd` | Cleanup, summaries |

Escalation and resume emit events but are not hook points.

## 3. Hook results

| Result | Effect |
|---|---|
| `continue` | No change |
| `annotate` | Adds sensitivity labels or findings without changing content; sensitivity policies (`notes/tools.md`) then apply |
| `rewrite` | Applies a patch to the content |
| `block` | Stops the action with a reason |
| `escalate` | Checkpoints and pauses for human decision |

Each hook **declares which results it may return**. This makes configuration checkable, e.g. a hook able to `block` at `beforeResponse` makes a `streamed` profile invalid (per Q5).

## 4. Execution rules

- Hooks run in declared order. `rewrite`s chain; the first `block` or `escalate` short-circuits.
- Every hook has a timeout.
- Every hook declares a failure mode:
  - `failClosed` — error or timeout is treated as `block`. **Default for guardrails.**
  - `failOpen` — error or timeout is treated as `continue`. Default for telemetry hooks.
- Every non-`continue` decision is written to the audit log with hook name and version. `continue` decisions are traced only.
- Eval replay supports two modes:
  - **Re-evaluate** — hooks run again against recorded traffic (tests a new or changed guardrail).
  - **Replay decisions** — recorded decisions are reused (isolates model or prompt changes).

## 5. Layering

Configuration layers, from highest to lowest:

1. **Org policy bundle** — mandatory hooks for the deployment
2. **Persona**
3. **Harness profile**

A lower layer may **add** hooks but may never remove or weaken one from a higher layer: it cannot drop a hook, change `failClosed` to `failOpen`, or narrow the results a mandatory hook may return. Violations are configuration errors at load time.

## 6. Hook sources

| Source | Notes |
|---|---|
| Declarative rules | No code. Label-based policies, allow/deny lists, schema checks on outputs, conditions in **CEL** (Common Expression Language). One rule works in all three implementations. |
| Native | Function in the implementation's language, for in-process logic. |
| Remote | HTTP or gRPC hook service, e.g. a shared PHI detector backed by Google DLP. Written once, used by all three implementations. |
| Model-judged | LLM classifier as a hook, with its own budget. Its model calls bypass the hook chain (traced only) so a guardrail cannot trigger itself. |

### CEL library research (2026-10-31)

Conclusion: CEL is viable in all three languages. TypeScript and Python libraries are young, so CEL is adopted **only** with a spec-defined subset, shared rule fixtures, and an evaluator abstraction. To be recorded as an ADR in Phase 2.

| Language | Library | Maintainer | Status (as checked) | Main risk |
|---|---|---|---|---|
| Java | `dev.cel:cel` (cel-java) | Google (official) | v0.15.0; compilation + runtime | Pre-1.0 versioning; otherwise most mature |
| TypeScript | `@bufbuild/cel` | Buf | v0.6.1 (Sep 2026), beta; ships cel-spec test data; used by `@bufbuild/protovalidate` 1.3.0 | API churn (redesigned at 0.3) |
| Python | `cel-expr-python` | Google (official) | v0.1.3; open-sourced Mar 2026; wraps cel-cpp; native wheels for Linux/macOS/Windows, Python ≥3.11 | Very new; repo read-only, no outside contributions yet |

Alternatives considered:
- `@marcbachmann/cel-js` (TS) — zero dependencies, single maintainer, full-spec support self-claimed. Backup option.
- `cel-js` (TS) — not updated since Jul 2025. Avoid.
- `cel-python` (Cloud Custodian, pure Python, v0.5.0, Beta) — documented semantic gaps (integer division, no type pre-check). Buf's Python validator moved from it (1.x) to a native extension (2.x). Fallback only.

Sources: [Google Open Source Blog — CEL-expr-python](https://opensource.googleblog.com/2026/03/announcing-cel-expr-python-the-common-expression-language-in-python-now-open-source.html) · [cloud-custodian/cel-python](https://github.com/cloud-custodian/cel-python) · [cel-python on PyPI](https://pypi.org/project/cel-python) · [dev.cel:cel on Maven Central](https://central.sonatype.com/artifact/dev.cel/cel) · [bufbuild/cel-es v0.3.0](https://github.com/bufbuild/cel-es/releases/tag/v0.3.0) · [@marcbachmann/cel-js](https://www.npmjs.com/package/@marcbachmann/cel-js) · npm and PyPI registry metadata.

### CEL safeguards

1. **agentry CEL subset**, defined in the spec: standard operators; macros `has`, `all`, `exists`, `exists_one`, `map`, `filter`; strings extension; JSON-like values only. No protobuf message types and no custom functions in 1.0.
2. **Shared rule fixtures**: expressions with expected results, including edge cases (integer division, null handling, missing fields, regex). All three implementations must pass.
3. **Compile and type-check at configuration load.** A rule that fails is a configuration error (fail closed).
4. **`RuleEvaluator` interface** in each implementation, so a library can be swapped without touching the spec.
5. **Pinned library versions**; rule fixtures re-run on every upgrade.

Plan B for Python if `cel-expr-python` stalls: evaluate rules through a remote hook.

## 7. Candidate domain concepts (for `domain.md`)

Hook · Hook point · Hook result · Hook decision · Guardrail · Guardrail pipeline · Failure mode · Policy bundle · Configuration layer · Finding · Rule (declarative) · CEL subset · Rule evaluator · Remote hook · Model-judged hook

## 8. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] `HookDefinition` (point, declared results, failure mode, timeout, source)
- [ ] `HookResult`
- [ ] `HookDecision` (audit event)
- [ ] `PolicyBundle`
- [ ] Declarative rule format (CEL embedding)
- [ ] agentry CEL subset definition
- [ ] ADR: CEL as the declarative rule language, library choices, safeguards

Fixtures:
- [ ] First `block` short-circuits later hooks
- [ ] Chained `rewrite`s apply in order
- [ ] Guardrail timeout → `block` (fail closed)
- [ ] Telemetry hook error → `continue` (fail open)
- [ ] `annotate` with `phi` triggers the sensitivity policy
- [ ] Persona attempts to remove an org hook → configuration rejected
- [ ] Profile attempts to weaken a mandatory hook → configuration rejected
- [ ] `streamed` profile with a blocking output hook → configuration rejected
- [ ] Hook returns a result it did not declare → treated as an error
- [ ] Model-judged hook's model call does not invoke hooks
- [ ] Replay in re-evaluate mode and in replay-decisions mode
- [ ] CEL rule fixtures: operators, each macro, integer division, null and missing fields, regex
- [ ] Rule outside the CEL subset → configuration rejected
- [ ] Rule that fails type-check → configuration rejected
