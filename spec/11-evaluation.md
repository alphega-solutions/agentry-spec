# Area 11 — Conformance, testing, and evaluation

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `intent.md` G1, G6, principle 5, §8 success criteria; `domain.md` (approved, incl. amendments); `notes/hooks.md` (replay modes); ADR-0001, 0002, 0006, 0011; Areas 1–10 (approved), esp. HOOK-062, CTX-001/032/083, PROV §11, PORT-130, TOOL-013

---

## 1. Scope

This area specifies:

1. **Conformance** — the format of conformance fixtures, how implementations run them, and how a conformance claim is made, including replaying another implementation's traces (`intent.md` §8).
2. **Test doubles** — the deterministic stand-ins that make fixtures and unit tests repeatable.
3. **Evaluation** — eval cases, graders, trace replay, converting traces into cases, and reports with a CI gate.

Command-line and web tooling are informative (Appendix A). This area is Tier 3; its replay modes come from `notes/hooks.md` §4.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `EVAL-`. Schemas for fixtures, CEL rule fixtures, trace bundles, eval cases, and reports are specified in Phase 4.

- **EVAL-000** Wherever this area compares or hashes JSON values — argument matching (EVAL-062), hook input hashes (HOOK-062), trace bundles — values **MUST** first be canonicalized with the JSON Canonicalization Scheme (RFC 8785). *(Clarifies HOOK-062.)*

## 3. Conformance fixtures

### 3.1 Format

- **EVAL-001** A conformance fixture is a data file, authored in YAML and published as JSON (ADR-0001). It **MUST** contain:

| Section | Contents |
|---|---|
| `id`, `title` | Stable identifier and description |
| `requirements` | The requirement IDs it verifies |
| `contract` | The contract version range it applies to |
| `features` | Optional features it needs (e.g. `binding.langchain`); empty for mandatory behaviour |
| `setup` | One or more tenants, principals, and sessions (including delegation chains); configuration artifacts or a shared set; initial port contents; virtual clock and ID-generator seed |
| `script` | Ordered steps: host actions (`run`, `resume`, `decide`, `close`, `cancel`) with reviewer principals where needed; scripted provider responses; stub behaviours (tools, MCP servers, HTTP endpoints, remote hooks); clock advances; crash points |
| `expect` | Event sequence patterns per session; run end reasons; session states; errors (category and code); port contents, including audit records; requests captured by stubs; things that must **not** occur |

- **EVAL-002** Fixtures **MUST** be deterministic. Values that vary between runs are matched by named placeholders that must bind consistently within a fixture (e.g. the same `$session` everywhere; two loads producing the same `$snapshotHash`).
- **EVAL-003** Fixtures **MUST** use synthetic data only: no real personal or health data, client details, or content from a private implementation (ADR-0011). Spec repository review enforces this.
- **EVAL-004** Event expectations **MUST** support: exact sequences, ordered subsequences, unordered sets (for parallel tool calls), presence and absence, and field matching. Fixtures **SHOULD** assert only what their requirements need.
- **EVAL-005** A **CEL rule fixture** contains an expression, the point whose variables it uses (HOOK §9.1), variable values, and the expected result or the expected failure (compile, type-check, or runtime).

### 3.2 Coverage

- **EVAL-010** Every normative requirement (`MUST`/`MUST NOT`) in the area specs, including requirements added by amendments, **MUST** be referenced by at least one fixture, unless the requirement is annotated *(untestable)* in its spec with the reason. The spec repository's CI **MUST** enforce this. Checks on the spec's own schemas (e.g. CFG-033) are spec-maintenance checks, listed separately. *(Introduces the untestable annotation for all areas.)*
- **EVAL-011** The conformance suite includes: CEL rule fixtures (ADR-0006, HOOK-110–114), the adapter test kit for every port (PORT-130), the provider adapter fixtures (PROV §11), and the golden trace bundles (§4.2).

## 4. Running conformance

### 4.1 The runner and the claim

- **EVAL-020** Each implementation **MUST** provide a **conformance runner** that loads the published fixtures for a contract version, drives the implementation with the test doubles (§5), and checks the expectations.
- **EVAL-021** Results **MUST** be reported per fixture — pass, fail, or skipped — with the fixture ID, its requirement IDs, and for failures the first unmet expectation, as JSON and JUnit XML.
- **EVAL-022** A fixture **MAY** be skipped only if its `features` include an optional feature the implementation declares unsupported (e.g. `binding.langchain`, TOOL-013).
- **EVAL-023** An implementation conforms to a contract version if, and only if, it passes every fixture it does not legitimately skip. A conformance claim **MUST** name the contract version and the declared unsupported features. Reference implementations **MUST NOT** declare any mandatory behaviour unsupported, and for contract 1.0 **MUST** pass the full suite (`intent.md` §8).
- **EVAL-024** Fixtures **MUST NOT** depend on real providers, real tools, or network access.

### 4.2 Cross-implementation traces

- **EVAL-025** Implementations **MUST** export a session as a **trace bundle**: its events, the blobs they reference, its snapshot, and its audit records, for one tenant. Bundles **MUST** validate against the published bundle schema.
- **EVAL-026** The spec repository publishes **golden trace bundles** (synthetic). Every implementation **MUST** replay each one (§6.3) and reproduce the recorded outcomes, and **MUST** export bundles that the other reference implementations can replay. This verifies `intent.md` §8: a trace recorded by any implementation replays in the others.

## 5. Test doubles

- **EVAL-030** Every implementation **MUST** provide the following test doubles, usable by its conformance runner and in unit tests.
- **EVAL-031** **Scripted providers** — provider adapters that pass PROV §11, return responses from a script (content parts, tool calls, usage, errors, capabilities), and **record every request** they receive for assertions. A fixture may declare several, as different providers, to exercise routing and failover. Summarizer, model-hook, and judge calls go to scripted providers too. A request beyond the script **MUST** fail the test.
- **EVAL-032** **Stubs** — scripted, call-recording stand-ins for `native` tools, MCP servers (including advertised schemas, for TOOL-092), HTTP endpoints, and remote hooks.
- **EVAL-033** **In-memory port adapters** — for every port in Area 10, each passing its adapter test kit (PORT-130).
- **EVAL-034** **Virtual clock and ID generator** — all time-dependent behaviour (TTLs, leases, timeouts, deadlines, timestamps, and the time component of UUIDv7) **MUST** read time from an injectable clock, and IDs **MUST** come from an injectable, seedable generator. *(Requires clock and ID injection in every implementation.)*
- **EVAL-035** **Crash injection** — the runner **MUST** be able to stop the implementation at named points — at least after a started record and before dispatch; after dispatch and before the outcome is recorded; after an event append and before the checkpoint save — and restart it against the same port contents.
- **EVAL-036** **Recorded vendor transcripts** — each native provider adapter (Claude, OpenAI) **MUST** pass the provider adapter fixtures offline against recorded wire-level request/response transcripts published with the suite.

## 6. Evaluation

### 6.1 Isolation

- **EVAL-040** Eval runs **MUST** use a dedicated eval tenant and dedicated port bindings, never production event logs, audit logs, or stores.
- **EVAL-041** In eval runs, every tool (whatever its `effect` or `egress`), MCP server, HTTP binding, and remote hook **MUST** be stubbed or replayed. Only model providers may be real, and only for content their sensitivity policies allow (PROV-053).
- **EVAL-042** Eval cases **MUST** use synthetic or converted (§7) data only.

### 6.2 Cases, runs, and graders

- **EVAL-043** An eval case **MUST** contain an ID, a persona reference, one or more principal inputs, and expectations; and **MAY** contain stub results, retrieval fixtures, attachments, scripted reviewer decisions for any escalation, and tags (e.g. `critical`).
- **EVAL-044** An eval run **MUST** declare its matrix — the models and harness profiles to compare — and a repeat count. Each case runs once per matrix cell per repeat, through the real harness with governance in force.
- **EVAL-050** Implementations **MUST** support these grader kinds, combinable per case:

| Grader | Checks |
|---|---|
| `schema` | Output validates against a JSON Schema, or equals an expected value |
| `trajectory` | Expected tools called, forbidden tools not called, optionally in order |
| `policy` | Expected or forbidden hook decisions and policy decisions |
| `escalation` | Escalated when it should, not when it shouldn't, with the expected source |
| `budget` | Tokens and cost under thresholds; latency only in live runs, not replay |
| `judge` | A rubric score from a model |

- **EVAL-051** A `judge` grader's model **MUST** come from a provider allowed for the content it reads (PROV-053), runs with no tools, and records its usage separately.
- **EVAL-052** Each grader result **MUST** record pass/fail or a score and the evidence (event IDs) it used.

### 6.3 Trace replay

- **EVAL-060** A case built from a trace bundle (§4.2) or a converted trace (§7) replays against a snapshot the run declares — the recorded one or a candidate — and the report states which. Either way, the replayed session **MUST** use the current deployment's providers, port bindings, secrets provider and endpoints, never the recording's.
- **EVAL-061** On replay, summaries and automatically retrieved content are always reused from the recording (CTX-083, CTX-032).
- **EVAL-062** Tool calls are answered from the recording. A call matches a recorded call when the tool is the same and its dispatched arguments (after hooks) are equal after canonicalization (EVAL-000); repeated identical calls match recorded occurrences in order. Agent-bound calls are answered with the recorded child result. An unmatched call receives a tool result error (`agentry.eval.unrecorded_call`, category `unavailable`, `retryable: false`, source `harness`), is reported as divergence, and — like delegation errors (ORCH-051) — **MUST NOT** by itself end the run.
- **EVAL-063** Replay supports two hook modes (HOOK-062):
  - **re-evaluate** — hooks run again on the replayed content;
  - **replay decisions** — recorded non-`continue` decisions are reused where the hook's input hash matches. Hooks with no matching recorded decision are re-evaluated; any that then return a non-`continue` result are reported as divergence. Converted traces (§7) always use re-evaluate, since conversion changes inputs.

## 7. Converting traces into cases and fixtures

- **EVAL-070** Implementations **MUST** provide an operation that converts a recorded session into an eval case or regression fixture draft.
- **EVAL-071** The conversion **MUST**:
  - run the deployment's redaction and labelling hooks over all content first, then refuse unless every part carrying a sensitivity label is redacted or replaced with synthetic content;
  - drop reasoning parts, hook input hashes, and blobs that are not redacted;
  - replace tenant, principal, session, event, and other identifying values with placeholders, and regenerate time-bearing IDs;
  - reference configuration by artifact `id@version` rather than copying the snapshot, so private configuration is not exported.
- **EVAL-072** Converted output is a draft: it **MUST** be marked as requiring human review before it joins an eval suite or the conformance suite. Labels cannot catch unlabelled sensitive content; human review is the final check.

## 8. Reports and CI gate

- **EVAL-080** An eval run **MUST** produce a report: per matrix cell — pass rate, per-grader results, token and cost totals, latency (live runs only), variance across repeats, divergences (EVAL-062, EVAL-063) — and differences from a declared baseline.
- **EVAL-081** A CI gate **MAY** be configured with thresholds. It **MUST** fail if any `critical` case fails in any cell, or a pass rate drops below its threshold.
- **EVAL-082** Reports **MUST** apply the redaction of the sensitivity policies in force and **MUST NOT** contain secret values.

## 9. Conformance fixtures for this area (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Canonicalization: key order and number forms compare equal | EVAL-000 |
| Fixture schema validation; unbound placeholder → runner error | EVAL-001, 002 |
| Unordered expectation for parallel calls; absence expectation fails when event occurs | EVAL-004 |
| CEL rule fixture: value, compile failure, runtime failure | EVAL-005 |
| Spec CI fails when a requirement loses its last fixture | EVAL-010 |
| Runner reports JSON and JUnit with requirement IDs | EVAL-020, 021 |
| Skipping a fixture without its feature declared unsupported → claim invalid | EVAL-022, 023 |
| Runner works with networking disabled | EVAL-024 |
| Exported bundle validates; golden bundles replay with recorded outcomes | EVAL-025, 026 |
| Scripted provider records requests; extra request fails; two providers drive failover | EVAL-031 |
| MCP, HTTP, and remote-hook stubs record calls; MCP schema drift scriptable | EVAL-032 |
| In-memory ports pass their test kits | EVAL-033 |
| Timestamps and UUIDv7 from virtual clock and seeded generator | EVAL-034 |
| Crash at each named point → recovery per HITL-091 and PORT-034 | EVAL-035 |
| Native adapters pass PROV fixtures against recorded transcripts | EVAL-036 |
| Eval run never touches production bindings; egress read tool still stubbed | EVAL-040, 041 |
| Eval case with scripted reviewer decisions | EVAL-043 |
| Matrix × repeats executed through governance | EVAL-044 |
| Each grader kind; judge on a disallowed provider never receives content; evidence recorded | EVAL-050–052 |
| Replay uses declared snapshot; summaries and retrieval reused | EVAL-060, 061 |
| Matching by canonical post-hook arguments; repeated calls in order; child results replayed; unmatched → divergence, run continues | EVAL-062 |
| Replay decisions: matching hash reused; missing decision re-evaluated; divergence reported | EVAL-063 |
| Conversion runs redaction hooks; refuses labelled unredacted parts; strips identifiers, reasoning, hashes; references config; marks draft | EVAL-070–072 |
| Report contents incl. divergences; critical failure fails gate; redacted | EVAL-080–082 |

## 10. Additions approved with this spec (2026-10-31)

All rules here are new; this is a Tier 3 area. Rules that affect approved areas are marked.

| ID | Proposed rule |
|---|---|
| EVAL-000 | **RFC 8785 canonical JSON** for matching and hashing (clarifies HOOK-062) |
| EVAL-001–005 | Fixture format (multi-tenant/multi-session setup, feature tags, stub scripts, audit expectations, unordered matching); CEL rule fixture format; synthetic data only |
| EVAL-010, 011 | **Every requirement needs a fixture, enforced by spec CI**; new *(untestable)* annotation for all areas; suite contents |
| EVAL-020–024 | Conformance runner per implementation; JSON/JUnit; skips only for declared optional features; **reference implementations skip nothing** |
| EVAL-025, 026 | **Portable trace bundles and golden bundles** to prove cross-implementation replay |
| EVAL-030–036 | **Mandatory test doubles**: request-recording scripted providers, stubs for tools/MCP/HTTP/remote hooks, in-memory ports, **injectable clock and seeded ID generator** (affects every implementation), crash injection, recorded vendor transcripts for native adapters |
| EVAL-040–042 | **Eval isolation**: dedicated tenant and bindings; every tool and remote dependency stubbed; only providers may be real |
| EVAL-043, 044 | Eval case and run format, including scripted reviewer decisions |
| EVAL-050–052 | Six grader kinds; judges follow sensitivity routing |
| EVAL-060–063 | Replay rules; call matching on canonical post-hook arguments; unmatched calls continue as divergences (exception to CORE-191 like ORCH-051); replay-decisions behaviour for unrecorded `continue` results |
| EVAL-070–072 | Conversion runs redaction hooks, strips identifiers and private config, and **always requires human review** |
| EVAL-080–082 | Report contents; CI gate with `critical` cases; redacted reports |

## Appendix A — Tooling (informative)

- **CLI first.** A command-line tool covers the scriptable needs: run conformance (`agentry test`), run evals (`agentry eval run`), compare runs (`agentry eval diff`), export and replay trace bundles, and convert traces (`agentry trace to-fixture`). It emits JSON and JUnit XML for CI. One TypeScript CLI can drive all three implementations through their conformance runners.
- **Static HTML reports.** The CLI can write a self-contained report per run — trace viewer, run comparison — covering most review needs without a server or authentication.
- **Web UI later.** A hosted UI earns its place when human graders or escalation reviewers need it. It reads the event and audit logs through their ports and eval reports as files; it does not run evals or keep its own copies.

## Amendment 2026-11-02 — from Phase 4 (schemas and fixtures)

Schemas: `schemas/eval/v1/bundle.yaml` (trace bundle), `case.yaml` (eval case and graders), `run.yaml` (eval run), `report.yaml` (eval report), `conformance-report.yaml` (runner report and claim). Fixture format: host actions `exportBundle`, `replay`, `convert` and `evalRun` with results `expect.bundle`, `expect.divergences`, `expect.draft` and `expect.report` (`conformance/schema/fixture.yaml`); golden trace bundles in `conformance/golden/`.

**Bundles and replay**

- EVAL-025: a bundle holds the session's events in sequence, every blob they reference with its bytes, its snapshot record, its audit records and, for a delegation chain, a bundle per child. It is exported unredacted, as stored (PORT-008), and is subject to the sensitivity policies of its content.
- EVAL-060–063: `replay` creates a new session in the given tenant from the bundle's first principal input of each turn, using the recorded snapshot (`recorded`) or the current configuration (`candidate`). Model calls are answered with the recorded responses, in order; summaries and retrieved content are reused (EVAL-061); tool calls are matched per EVAL-062; recorded decisions on escalations are reapplied in order. A divergence is reported as `{kind: unrecorded_call, callId, tool}` (EVAL-062) or `{kind: hook_decision, hook, eventId}` (EVAL-063). A model call beyond the recording ends the replayed run `failed` (`agentry.eval.unrecorded_model_call`, `fatal`).

**Eval runs**

- EVAL-040: an eval run is refused (`configuration`, `agentry.eval.production_binding`) unless its deployment's `environment` is `eval`; its tenant is used for nothing else.
- EVAL-041: in an eval run every tool, MCP server, HTTP endpoint, remote and native hook and vector store is answered from the case's stubs (or the replayed recording); a call with no stub behaviour fails the case (`unavailable`, `agentry.eval.unstubbed_call`), never reaching a real endpoint.
- EVAL-044: each case runs once per matrix cell per repeat, as its own session, with governance in force: hooks, the taint rule, approval and routing apply. Scripted reviewer decisions answer escalations; an escalation no rule matches leaves the case failed with its session suspended.
- EVAL-050: a case passes in a repeat when every grader passes and the run neither made an unstubbed call (EVAL-041) nor left an escalation unresolved (EVAL-044); a case that fails for either reason records it as the result's `code` (`agentry.eval.unstubbed_call`, `agentry.eval.unresolved_escalation`), and its graders still run. `schema` checks the final structured output, or the final output against `equals` after canonicalization; `trajectory` checks dispatched tool calls (`tool.call` events), in order when `ordered`; `policy` matches `hook.decision` and `policy.decision` events; `escalation` checks whether an escalation was raised and, if given, that every pending action has that source; `budget` checks the session's tokens and cost (latency only in live runs); `judge` asks its model for a score in [0, 1] and passes at or above `threshold`.
- EVAL-051: a judge reads the final response and the case's inputs, through a model allowed for every label on that content; if none is allowed, the judge grader fails with `agentry.eval.judge_not_allowed` and receives nothing. Its usage is recorded on its grader result, not in the cell's tokens.
- EVAL-080, EVAL-081: a cell's `passRate` is passing results over results; `variance` is the mean over cases of the variance of their 0/1 pass results across repeats. The gate fails if any case tagged `critical` fails in any cell, or a cell's pass rate is below `gate.minPassRate`.

**Conversion**

- EVAL-070–072: `convert` returns `{review: required, kind: case|fixture, content}`, where `content` is an eval case or a fixture draft with placeholders for identifying values and configuration referenced by `id@version`. If any labelled part would remain unredacted after the deployment's redaction and labelling hooks run, conversion is refused (`policy`, `agentry.eval.unredacted_content`) and returns nothing.

**Verified elsewhere**

- Requirements on the runner, the test-double kit and the spec repository itself are listed with how they are verified under `verifiedElsewhere` in `conformance/coverage.yaml`. The spec repository's own obligations (EVAL-002 placeholders, EVAL-010 coverage) are exercised by `tools/selftest.py` in spec CI.

**Readings settled with the Area 11 fixtures**

- EVAL-044: an eval run executes cells in declared order, then repeats, then cases, each case graded before the next starts. Every run of a case starts from the case's stub behaviours afresh; setup stubs of the surrounding fixture do not apply inside an eval run. A cell's `model` replaces the persona's primary model for that cell. An unstubbed call is delivered to the model as a tool result error and the run continues (as EVAL-062).
- EVAL-050: a judge's model answers with a `structured` part `{score}`, a number in [0, 1]. Grader `evidence` lists event IDs in log order. A grader that cannot run records `passed: false` and a `code` on its result.
- EVAL-080: a cell's `tokens` are `inputTokens + outputTokens` over its sessions (PROV-071), and `cost` likewise, both excluding judge calls; `variance` is the population variance p(1−p) of each case's pass indicator across repeats, averaged over cases; `results` are listed in execution order. A report with no gate configured has `gate: {passed: true, failures: []}`; a pass rate is below the threshold only when strictly less. A run's `baseline` names the run ID of an earlier report available to the runner.
- EVAL-070: conversion runs the redaction and labelling hooks of the configuration in force when `convert` is called, emits no events into the recorded session, and drops every blob, so a draft fixture carries no `blobStore` contents.
- CTX-001, EVAL-025 *(amends the Area 1 event catalog payloads)*: `turn.started` carries the principal's message as it enters context, with its provenances and labels, so every turn's input is in the event log. On the first turn it is emitted after the `sessionStart` hooks have run (and after their `hook.decision` events), so content those hooks rewrite or redact is persisted only in its rewritten form (CORE-080, PORT-008); later turns have no `sessionStart` hooks. Automatic retrieval (CTX-031) follows `turn.started`, and retrieved parts are recorded by `context.retrieved`, not in the `turn.started` message. A `hook.decision` with result `rewrite` carries `replacementRef`: a BlobStore blob (`application/json`) holding the content as rewritten — an array of parts, each with the provenance and labels the harness assigned (HOOK-021) — so rewrites are reproduced from events and reused under replay-decisions (EVAL-063). The blob carries the labels of its parts and is retained with the session's other blobs; an audit record's copy of the payload references it and does not extend its retention.
- CFG-050, EVAL-025: a snapshot holds effective values, defaults included (except those of fields with a merge rule, which stay absent unless set; Area 2 amendment 2026-11-14): an agent-bound tool's `idempotent` is `true` (ORCH-002), and a hook's `failureMode` is its purpose's default when not set (HOOK-001). Defaults are filled only within objects present in the artifact: an absent optional object (for example a tool's `retry`) stays absent and is not materialised with its defaults.
- EVAL-060, EVAL-062: under replay, a tool call answered from the recording emits `tool.call` and `tool.result` as a dispatched call would, with the recorded output, and consults no IdempotencyStore and writes no idempotency record, since nothing is dispatched. An agent-bound call answered from the recording carries no `childSessionId` and creates no child session — an exception to the Area 8 reading that every agent call has a child; the recorded child's bundle is used only when the call is not answered from the recording and the child is itself replayed.
- EVAL-060, EVAL-061: `snapshot: candidate` uses the configuration the runner loaded for the replay; `recorded` uses the bundle's snapshot record with its deployment bindings replaced by the current deployment's (EVAL-060 as amended 2026-11-14). An eval run's `replay.snapshot` takes the same values, or the hash of a stored snapshot.
- EVAL-026, EVAL-044: a case's `replay.bundle` and an action's `bundle` are paths relative to `conformance/` in the conformance suite (for example `golden/single-lookup.yaml`), or to the eval suite's root. A replayed case takes its persona, principal and inputs from the bundle, so `persona` and `inputs` are required only for cases that are not replayed.
- EVAL-023: a conformance report's `conforms` is `true` only if no result has `status: fail` and every `skip` names, in `skippedFor`, one of the report's `unsupportedFeatures` that the fixture lists in its `features`; the report schema rejects `conforms: true` alongside a failure, and runner validation checks the skip rule.
- EVAL-004: event-pattern modes are `sequence` (every event of the session matches the items one-to-one, in log order), `subsequence` (the items match distinct events in log order, other events allowed), `unordered` (one-to-one, in any order) and `contains` (the items match distinct events in any order, other events allowed). In `sequence` and `unordered` mode, `checkpoint.saved` events are ignored unless an item names that type, since how many an implementation emits is not fixed.
- EVAL-041, EVAL-062: in a replayed eval case, a tool call the recording does not answer is a divergence (`unrecorded_call`), not an unstubbed call: it gives the case no failure `code`, and the case passes or fails on its graders alone.
- HOOK-062, EVAL-063 *(amends the Area 5 reading of HOOK-062)*: a hook's `inputHash` also excludes `principal.tenant`, which always equals the excluded `tenant`, so a recording replayed into an eval tenant (EVAL-040) reuses its recorded decisions.
- EVAL-024: spec CI rejects any fixture URL with a network scheme whose host is outside the reserved test domains (RFC 2606, RFC 6761); in-process schemes (`memory://`, `secret://`) are allowed.
- EVAL-036: pending until Phase 5, which publishes the recorded vendor transcripts; until then it is listed under `pending` in `conformance/coverage.yaml` and must be resolved before the first release.

## Amendment 2026-11-14 — replay never uses the recording's bindings (post-Phase 4 review)

Requirement text above has been edited where noted.

- **EVAL-060** (text above edited). A snapshot holds the whole effective configuration, including the `Deployment`. Replaying with `snapshot: recorded` loaded that snapshot "as given", so a replay of a production recording ran on the recording's bindings. Its events, checkpoints, blobs and audit records went to the production stores; under `reEvaluate`, remote hooks were called at their production endpoints with the recorded content, which is exported unredacted (PORT-008); model hooks called production providers; and the replaying process needed production secrets. This contradicted EVAL-040 and EVAL-041, and the eval run's `environment: eval` check did not reach the replayed session's snapshot.
- **The replayed configuration.** Under `recorded`, the replayed session's snapshot is the recorded snapshot with these deployment fields taken from the **current** deployment: `environment`, `providers`, `ports` (including the secrets provider and any vector store), `retention`, `legalHolds`, `mcpServers`, `remoteHooks` and `httpEndpoints`, each binding with its own credentials. Everything else is the recording's: every policy bundle, persona, profile, tool and hook artifact, and the deployment's `policyBundles`, `attachmentSources` and `priceTable`. In an eval run, the current deployment is the run's eval deployment (EVAL-040). `candidate` is unchanged: it already uses the current configuration, bindings included.
- **Loading.** The composed configuration is loaded like any other (Area 2), before the replayed session is created. If it does not load (for example, the recording references a provider, MCP server, HTTP endpoint or remote hook that the current deployment does not declare, CFG-011), the replay is refused with that `configuration` error. No session is created and nothing is sent.
- **Snapshot hash.** The replayed session is pinned to the composed snapshot, and its events carry that hash (CFG-054). The hash equals the recorded one exactly when the current deployment's bound fields equal the recording's. The replayed session's `session.created` carries `replay: {sessionId, snapshotHash}`, naming the recorded session and its snapshot, so the replayed events always show which recording and configuration they reproduce. This is also how a report's `snapshot: recorded` (EVAL-060) is traced back to its hash.
- **Fixtures.**
  - New: `eval.replay-recorded-current-bindings`.
  - The existing replay fixtures are unchanged. Each replays under a deployment identical to the recording's, so the composed snapshot is the recorded one and its hash is unchanged.

## Amendment 2026-11-14 — matching by assignment; port shapes (post-Phase 4 review)

- **EVAL-004.** The fixture format said that `unordered`, `contains` and `$contains` match items to distinct elements, but not how. A greedy runner, where each item takes the first element it matches, fails where a valid assignment exists. For example, items `{type: tool.result}` then `{type: tool.result, payload: {callId: c1}}` fail when c1's result comes first. With placeholders, `subsequence` had the same ambiguity. Two runners could disagree on the same implementation.
  - These modes and `$contains` now succeed when any valid assignment exists, and runners must search for one.
  - Placeholder bindings are those of the first assignment in canonical order: items in listed order, each given the earliest element that still lets the rest match.
  - Placeholders inside `$not`, `$count`, `$every` and `absentEvents` never bind there.

  See `conformance/README.md`.
- **Port shapes.**
  - `expect.ports.snapshotStore` is documented as `{tenant: {<hash>: snapshot record}}`.
  - `blobStore` records include `labels`, as the Area 10 reading already shows.
  - In harness fixtures, blob `data` is the bytes as padded standard base64, whatever the media type. Port cases keep UTF-8 text or `{base64}`.
- **Fixtures.** New: `eval.format-matching-assignment`.
