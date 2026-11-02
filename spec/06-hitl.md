# Area 6 — Human-in-the-loop

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `domain.md` (approved, incl. HITL amendment); notes `hitl.md`, `security.md` (settled); ADR-0004, 0008, 0014, 0015; Areas 1–5 (approved)

---

## 1. Scope

This area specifies escalations: when they are created, what they contain, who may decide them, what each decision does, how decisions are submitted and applied, what happens on expiry, and how interrupted runs are recovered.

agentry records escalations and accepts decisions. Notifying reviewers, routing work, and review user interfaces are the host's responsibility (ADR-0004). Appendix A describes integration with workflow engines.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `HITL-`. The schemas `Escalation`, `PendingAction`, and `Decision` are specified in Phase 4.

## 3. Raising an escalation

- **HITL-001** An escalation **MUST** be created when any of the following occurs. Area 8 may define further sources for nested sessions.

| Source | Trigger |
|---|---|
| `taint` | The taint rule's outcome is `escalate` (HOOK-122) |
| `approval` | A call's effective approval is `always`; or `policy` and an approval rule is true, errors, or none is declared (TOOL-035, HOOK-131, HOOK-132) |
| `hook` | A hook returns `escalate` (HOOK-033) |
| `recovery` | A non-idempotent mutating call has an unknown outcome (TOOL-062, §10) |

- **HITL-002** A session **MUST** have at most one open escalation at a time. All escalations arising while processing one step's tool calls **MUST** be grouped into one escalation, with one pending action each (TOOL-033). A new escalation may be raised in the same step after the previous one is resolved (for example, TOOL-036 re-escalation).
- **HITL-003** When an escalation is created, the implementation **MUST** checkpoint the session, emit `escalation.raised` carrying the escalation record (subject to the redaction rules for events, CORE-154), end the run with `escalated`, and move the session to `suspended` (CORE-020).

## 4. The escalation record

- **HITL-010** An escalation **MUST** contain:
  - ID (UUIDv7), session ID, run ID, turn, step, tenant, snapshot hash
  - the escalation source(s) and reason code(s)
  - one or more pending actions (HITL-011)
  - the provenances that tainted the session, when any pending action has source `taint` (HOOK-126)
  - the reviewer requirements that apply (§5)
  - created and expiry times (expiry = created time + `suspendedTtl`)
- **HITL-011** Each pending action **MUST** have an ID and contain its kind and the decisions it allows:

| Kind | Raised by | Contents | Allowed decisions |
|---|---|---|---|
| `tool_call` | Taint rule, approval, or a hook at `beforeToolCall` | Tool reference, arguments, source, reason code | `approve`, `reject`, `edit` |
| `content` | A hook at any other point | Hook point, content under review, source, reason code | `approve`, `reject`; also `edit` at `beforeResponse` |
| `recovery` | Recovery (§10) | Tool reference, arguments, idempotency key | `confirm` |

- **HITL-012** An escalation **MUST** remain retrievable while its session is `suspended`. It is stored in the checkpoint store, which is tenant-scoped (ADR-0014).

## 5. Reviewers

- **HITL-020** Every decision **MUST** be made by a reviewer: a human principal supplied by the host, belonging to the session's tenant. The reviewer is recorded with the decision and never replaces the session principal (ADR-0014). The only exception is an expiry rejection (§9), recorded as `decidedBy: expiry`.
- **HITL-021** Policy bundles and personas **MAY** declare **reviewer rules**: per escalation source, a CEL expression (HOOK-110) with variables `reviewer` (fields as `principal`, HOOK §9.1), `principal` (the session principal), and `escalation` (`source`, `reasonCode`, and `pendingActions` with each action's `kind` and tool `id`). Reviewer rules merge by `union`: a reviewer must satisfy every applicable rule. *(Extends CFG-070 and CFG-080.)*
- **HITL-022** A decision from a reviewer who is not human, belongs to another tenant, or fails any applicable reviewer rule **MUST** be refused with error category `unauthorized`.
- **HITL-023** A reviewer **MUST NOT** be the session's principal, unless a policy bundle sets `allowSelfApproval` for that escalation source (merge rule `stricter`, order `false` → `true`). Self-approval **MUST NOT** be allowed for sources `taint` or `recovery`.
- **HITL-024** Reviewer rules **MAY** set `requiredApprovals` (default 1). The effective value for a pending action is the highest `requiredApprovals` among the rules that apply to it. Approvals **MUST** come from distinct reviewers.

## 6. Reviewer view

- **HITL-030** The implementation **MUST** provide, for a given escalation and reviewer, a **reviewer view**: the escalation record and each pending action's content.
- **HITL-031** In the reviewer view, each part **MUST** be redacted unless the reviewer satisfies the `reviewerRule` of every sensitivity label on that part. A label whose sensitivity policy declares no `reviewerRule` does not restrict reviewers. Within `sensitivityPolicies`, `reviewerRule` merges by `union` (a reviewer must satisfy every layer's rule). *(Extends CFG-070.)*
- **HITL-032** The reviewer view **MUST NOT** include secret values, credentials, or reasoning parts.

## 7. Decisions

### 7.1 Submitting decisions

- **HITL-040** Decisions are submitted with `decide()`, which records them without resuming. `resume()` **MAY** also carry decisions, which are recorded as if submitted with `decide()` first.
- **HITL-041** A decision **MUST** contain: decision ID (UUIDv7), escalation ID, pending action ID, decision type, reviewer, timestamp; for `edit`, the replacement content; for `confirm`, the stated outcome.
- **HITL-042** Submitting a decision ID that has already been recorded **MUST** be acknowledged without effect. This makes `decide()` and `resume()` safe to retry with the same batch.
- **HITL-043** A decision type not allowed for its pending action (HITL-011) **MUST** be refused with error category `invalid_input`.
- **HITL-044** Decisions are immutable. Every recorded decision **MUST** be written to the audit log with the snapshot hash; an `edit` **MUST** record both the original and the replacement.

### 7.2 When a pending action is decided

- **HITL-050** With `requiredApprovals` of 1, the first `approve`, `reject`, `edit`, or `confirm` decides the action.
- **HITL-051** With `requiredApprovals` greater than 1:
  - any single `reject` rejects the action immediately;
  - each `approve` counts toward the original content, and each `edit` counts toward its replacement content;
  - the action is approved when the required number of distinct reviewers have approved the **same** content (the original, or one identical replacement). Until then it stays undecided.

### 7.3 Effects

| Decision | Pending action | Effect |
|---|---|---|
| `approve` | `tool_call` raised at stages 5 or 7 | Processing continues at the next stage (TOOL-036) |
| `approve` | `tool_call` raised by a `beforeToolCall` hook | The hook chain resumes at the next hook (HOOK-034), then the remaining stages |
| `approve` | `content` | The hook chain resumes at the next hook (HOOK-034) |
| `reject` | `tool_call` | The call is not dispatched; the model receives a `policy` error (`agentry.hitl.rejected`); the turn continues |
| `reject` | `content` at `sessionStart`, `beforeModelCall`, `afterModelCall`, or `beforeResponse` | The run ends `blocked` with the fallback message (CORE-181) |
| `reject` | `content` at `afterToolCall` | The result is withheld; the model receives a `policy` error (`agentry.hitl.rejected`) |
| `edit` | `tool_call` | See HITL-061 |
| `edit` | `content` at `beforeResponse` | See HITL-062 |
| `confirm` | `recovery` | The stated outcome is recorded in the idempotency store and delivered to the model: `succeeded` as an `ok` result (with output if supplied), `failed` as an error of category `unavailable`, `retryable: false` (`agentry.hitl.confirmed_failed`). The call is never re-dispatched |

- **HITL-060** Implementations **MUST** apply decisions with the effects above.
- **HITL-061** Edited tool arguments **MUST** carry provenance `reviewer` (trusted) and at least the sensitivity labels of the arguments they replace. They re-enter the tool pipeline at stage 2 (argument validation), pass stage 4 (assurance), skip stage 5 (taint rule), and run **all** `beforeToolCall` hooks (stage 6). Stage 7 treats the edit as approval. A hook may still block or escalate the edited arguments.
- **HITL-062** An edited response **MUST** carry provenance `reviewer` and at least the labels of the response it replaces, **MUST** satisfy any output schema (CORE-130), and **MUST** pass through **all** `beforeResponse` hooks from the first.
- **HITL-063** An `edit` that fails validation **MUST** be refused with error category `invalid_input`; the pending action stays undecided.

## 8. Resuming

- **HITL-070** `resume()` **MUST** be accepted only when every pending action in the open escalation is decided. Otherwise it fails with error category `conflict` (`agentry.hitl.pending`), any decisions it carried remain recorded, and the session stays `suspended`.
- **HITL-071** A `resume()` whose escalation was already resumed **MUST** return the original outcome without new work (CORE-053).
- **HITL-072** On an accepted `resume()`, the implementation **MUST** emit `escalation.resolved`, continue the suspended turn (CORE-080), and deliver any held results in request order (TOOL-032, TOOL-033).

## 9. Expiry

- **HITL-080** Escalations **MUST NOT** be approved automatically under any circumstances.
- **HITL-081** A harness profile **MAY** set `onExpiry` to `close` (default) or `reject`. Merge rule `stricter`, order `close` → `reject`. *(Extends CFG-090.)*
- **HITL-082** When `suspendedTtl` elapses with undecided pending actions:
  - `close`, or any undecided `recovery` action: the session closes `expired` (CORE-020). Rejecting does not establish a recovery outcome, so `reject` never applies to recovery actions.
  - `reject`: every undecided action receives an expiry rejection (`decidedBy: expiry`) and the session remains `suspended`, now fully decided. The host continues it with `resume()`. If no `resume()` arrives within a further `idleTtl`, the session closes `expired`.

## 10. Recovery of interrupted runs

- **HITL-090** An active run **MUST** hold a renewable lease recorded with its checkpoint. A run whose lease lapses (for example, after a process crash) is **orphaned**.
- **HITL-091** An implementation **MUST** detect orphaned runs, at the latest when the session is next accessed, and end them:
  - if a non-idempotent mutating call has a started record and no outcome (TOOL-062): raise a `recovery` escalation and end the run `escalated`;
  - if an idempotent mutating call was in flight: re-dispatch it with the same idempotency key, then continue the run;
  - otherwise: end the run `failed`.
- **HITL-092** While a run is orphaned but not yet ended, `run()` and `resume()` **MUST** first perform HITL-091 rather than failing with `conflict`.

## 11. Finding pending escalations

- **HITL-100** Implementations **MUST** provide `listPendingEscalations`, returning, for one tenant only, the open escalations of `suspended` sessions whose `suspendedTtl` has not elapsed.
- **HITL-101** agentry includes no notification transport, and implementations **MUST NOT** require one. Hosts learn of escalations from `escalation.raised` events or `listPendingEscalations`.

## 12. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Each source creates an escalation, including an approval-rule error | HITL-001 |
| Two calls escalate in one step → one escalation, two pending actions | HITL-002 |
| Re-escalation after approval in the same step → second escalation after the first resolves | HITL-002 |
| Escalation → checkpoint, `escalation.raised` with record, run `escalated`, session `suspended` | HITL-003 |
| Record contents, including tainting provenances for `taint` | HITL-010 |
| `beforeToolCall` hook escalation is a `tool_call` action allowing `edit` | HITL-011 |
| Escalation retrievable while suspended; other tenant cannot retrieve | HITL-012 |
| Reviewer recorded; never replaces session principal | HITL-020 |
| Non-human, other-tenant, or rule-failing reviewer → `unauthorized` | HITL-021, 022 |
| Self-approval refused by default; allowed for `approval` by bundle; refused for `taint` and `recovery` even if set | HITL-023 |
| Lower bundle enabling self-approval that a higher bundle set to `false` → rejected | HITL-023 |
| Highest `requiredApprovals` applies | HITL-024 |
| Reviewer view redacts parts the reviewer isn't cleared for; no secrets or reasoning | HITL-030–032 |
| `decide()` records without resuming; `resume()` with decisions records them | HITL-040 |
| Decision record contents; audited; edit records before and after | HITL-041, 044 |
| Resubmitted batch with already-recorded IDs → acknowledged; new ones recorded | HITL-042 |
| Decision type not allowed → `invalid_input` | HITL-043 |
| Two required approvals: one insufficient; reject rejects; matching edits approve; differing edits stay undecided | HITL-050, 051 |
| Approve at stage 7 → continues at stage 8 | HITL-060 |
| Approve a `beforeToolCall` hook escalation → next hook runs | HITL-060 |
| Reject tool call → `policy` error, turn continues | HITL-060 |
| Reject at each content point → outcome per table | HITL-060 |
| Edit arguments → `reviewer` provenance, labels kept, validated, taint skipped, all hooks run | HITL-061 |
| Edited response must satisfy output schema and pass all `beforeResponse` hooks | HITL-062 |
| Invalid edit → `invalid_input`, action undecided | HITL-063 |
| Confirm `succeeded` → `ok` result, no re-dispatch; `failed` → `agentry.hitl.confirmed_failed` | HITL-060 |
| Partial decisions → `conflict` (`agentry.hitl.pending`), decisions kept | HITL-070 |
| Replayed resume → original outcome | HITL-071 |
| Accepted resume → `escalation.resolved`, turn continues, results in order | HITL-072 |
| Nothing is ever auto-approved | HITL-080 |
| `onExpiry` tightening accepted; loosening rejected | HITL-081 |
| Expiry with `close` → `closed (expired)` | HITL-082 |
| Expiry with `reject` → expiry rejections; resume continues; no resume → closes after `idleTtl` | HITL-082 |
| Expiry with an undecided recovery action → closes `expired` even under `reject` | HITL-082 |
| Crash mid non-idempotent call → orphaned run ends `escalated` with recovery action | HITL-090, 091 |
| Crash mid idempotent call → re-dispatched with same key | HITL-091 |
| `run()` on an orphaned session triggers recovery instead of `conflict` | HITL-092 |
| `listPendingEscalations` returns only one tenant and excludes elapsed TTLs | HITL-100 |
| Implementation operates with no notification transport configured | HITL-101 |

## 13. Additions approved with this spec (2026-10-31)

| ID | Proposed rule |
|---|---|
| HITL-001 | Sources list is open to Area 8 additions |
| HITL-002 | **At most one open escalation per session**; grouping per step; later re-escalation allowed |
| HITL-011 | `beforeToolCall` hook escalations are `tool_call` actions (so `edit` is allowed) |
| HITL-012 | Escalations stored in the checkpoint store |
| HITL-020, 022 | Reviewers must be human and in the session's tenant; refusals use `unauthorized`; expiry rejections recorded as `decidedBy: expiry` |
| HITL-021 | Reviewer-rule variables; rules merge by `union` (extends CFG-070, CFG-080) |
| HITL-023 | `allowSelfApproval` field with `stricter` merge |
| HITL-024 | Highest applicable `requiredApprovals` wins (a derived value, not a merged field) |
| HITL-031 | New `reviewerRule` on sensitivity policies, merged by `union` (extends CFG-070) |
| HITL-032 | Reviewer view never includes secrets, credentials, or reasoning |
| HITL-040, 042 | **New `decide()` operation**; resubmitted decision IDs acknowledged without effect |
| HITL-043, 063 | Disallowed decision types and invalid edits fail with `invalid_input` |
| HITL-051 | Multi-approver counting rules for approve vs edit |
| §7.3 | Error codes `agentry.hitl.rejected` and `agentry.hitl.confirmed_failed`; confirmed failures are non-retryable `unavailable` |
| HITL-061, 062 | **Edits re-run validation and all hooks** (only the taint rule and approval are skipped) and keep the replaced content's labels |
| HITL-070 | Incomplete `resume()` fails with `conflict` (`agentry.hitl.pending`) |
| HITL-081 | `onExpiry` field and strictness order (extends CFG-090) |
| HITL-082 | **Amends Area 1 CORE-020:** with `onExpiry: reject`, an expired suspended session stays `suspended` (fully decided) until `resume()`, then closes after a further `idleTtl` if none arrives |
| HITL-090–092 | **Amends Area 1:** run leases, orphaned-run detection, and recovery on next access |
| HITL-100 | `listPendingEscalations` excludes sessions whose TTL has elapsed |
| HITL-101 | Implementations must not require a notification transport |

## Appendix A — Integration with workflow engines (informative)

agentry sessions are designed to run as steps inside a host's workflow engine (ADR-0004).

- **Temporal and similar durable-execution engines.** Call `run()` from an activity. When the run ends `escalated`, the workflow waits on a signal carrying the reviewer's decisions, then calls `resume()` from another activity. Use the escalation ID as the signal correlation key. Activity retries are safe because `resume()` and `decide()` are idempotent.
- **Callback-style engines (GCP Workflows, AWS Step Functions).** On `escalation.raised`, the host creates a callback and stores its token against the escalation ID. The review UI submits decisions, and the callback handler calls `resume()`. Use the engine's timeout as a backstop, set no longer than `suspendedTtl`.
- **Without a workflow engine.** Poll `listPendingEscalations`, or subscribe to `escalation.raised` events, and call `resume()` when the review UI reports all actions decided.

## Amendment 2026-10-31 — from Area 8

- HITL-001–003, HITL-010: escalations raised in a child are mirrored on every ancestor with the same pending actions; each action keeps its original source and is marked `delegated` (ORCH-060, ORCH-061).
- HITL-100: decisions are accepted, and escalations listed, at the root only (ORCH-063).
- HITL-081: a chain uses its earliest `suspendedTtl` and strictest `onExpiry` (ORCH-065).
- HITL-091: recovery handles in-flight children first, deepest first (ORCH-071).

## Amendment 2026-11-01 — from Phase 4 (Area 4 fixtures)

- **HITL-091** is replaced by this ordered procedure for an orphaned run's in-flight tool calls, applied per call:
  1. **Outcome recorded** in the idempotency store: the call re-enters the tool pipeline at stage 9 with the recorded outcome (result checks, `afterToolCall` hooks, recording), so redaction applies exactly as for a live call (TOOL-073). Nothing is re-dispatched, whatever the tool's idempotency.
  2. **Read call** with no recorded outcome: re-dispatched.
  3. **Idempotent mutating call** with a started record and no outcome: re-dispatched with the same idempotency key.
  4. **Non-idempotent mutating call** with a started record and no outcome: raises a `recovery` pending action.

  If any call took step 4, the run ends `escalated` once the other calls are processed. Otherwise the run continues. A run with no in-flight call ends `failed`. A continuing orphaned run keeps its `runId` and emits no new `run.started`. The host call that triggered recovery (HITL-092) proceeds with its own run after the orphaned run ends, and receives its own outcome.

## Amendment 2026-11-01 — from Phase 4 (schemas and fixtures)

Schemas: `schemas/core/v1/hitl.yaml` (`escalation`, `pendingAction`, `decision`, `reviewerView`); `escalation.raised` carries the `escalation` record.

**The record (HITL-010, HITL-011)**

- The escalation carries `id`, `sessionId`, `runId`, `turn`, `step`, `tenant`, `snapshotHash`, `sources` and `reasonCodes` (each the distinct values of its pending actions, in order of first appearance), `pendingActions` in request order, `taintProvenances` (when any action has source `taint`, in order of first entry, HOOK-126), `createdAt` and `expiresAt`.
- Every pending action carries `id`, `kind`, `source`, `reasonCode`, `allowedDecisions` (exactly the set HITL-011 gives its kind), `reviewerRequirements`, and the contents of its kind; `hook` (`id@version`) when its source is `hook`; and `labels`, the labels of the content under review. Reviewer requirements are per action (HITL-024): the effective `requiredApprovals`, whether self-approval is allowed for its source (HITL-023), and the applicable reviewer rules.
- Reason codes for harness sources: `agentry.taint.mutating` and `agentry.taint.egress` (the taint condition whose outcome applied; `mutating` when both give `escalate`); `agentry.approval.always`, `agentry.approval.rule`, `agentry.approval.rule_error` and `agentry.approval.no_rules` (TOOL-035, HOOK-131, HOOK-132); `agentry.recovery.unknown_outcome`. A hook's own reason code is used for source `hook`.

**Host operations**

- HITL-030: the reviewer view is returned by `getReviewerView(tenant, escalationId, reviewer)`. An escalation of another tenant is `not_found`, as for any tenant-scoped object (ADR-0014). A reviewer who is not human or not in the tenant is refused with `unauthorized` (HITL-022); reviewer-rule failures do not refuse the view — clearance is per part (HITL-031). Each pending action's content is its one `tool_call` part (`tool_call` and `recovery` actions) or the parts under review (`content` actions), with the decisions recorded so far and whether it is decided. A part the reviewer is not cleared for keeps `type`, `provenance` and `labels`, is marked `redacted: true`, and carries none of its content.
- HITL-100: `listPendingEscalations(tenant)` returns escalation records. Neither operation changes state or emits events.

**Decisions**

- HITL-021: reviewer rules are evaluated per pending action, for the rules of that action's source; `escalation.source` and `escalation.reasonCode` are the action's.
- HITL-040–043: `decide()` and `resume()` validate their decisions as one batch. If any decision is refused (`unauthorized`, `invalid_input`, or a pending action ID not in the open escalation, `not_found`), none of the batch is recorded and the error's `details.decisionId` names the first refused decision. An already recorded decision ID is acknowledged, not refused. A batch that records but leaves actions undecided makes `resume()` fail with `conflict` (HITL-070) after recording.
- HITL-044: a decision is audited as a `decision` audit record whose `details` are the `decision` record, plus `original` for an `edit`. Expiry rejections are audited too, with `decidedBy: expiry`, no reviewer, and the expiry time as timestamp.
- HITL-051: two replacements are identical when their RFC 8785 canonical JSON is equal.
- HITL-072: `escalation.resolved` lists every decision ID recorded for the escalation, in recording order.

**Ordering, timing and events** (settled with the Area 6 fixtures)

- HITL-003: the events of raising an escalation are, in order, `escalation.raised`, `checkpoint.saved`, `run.ended` (`escalated`); the checkpoint never runs ahead of the event log (PORT-035). The `escalation` audit record's `details` are the escalation record.
- HITL-040: `decide()` stores decisions in the checkpoint store and the audit log and emits no events. Decisions in one batch are recorded in the order submitted.
- HITL-042: a resubmitted decision ID is acknowledged without effect even if its other fields differ. For CORE-053, a decision ID is *applied* once an accepted `resume()` has acted on it; a `resume()` whose decisions were all recorded earlier by `decide()` is a new resume, not a replay.
- Refusal codes: `agentry.hitl.reviewer_refused` (`unauthorized`, HITL-022, HITL-023), `agentry.hitl.decision_not_allowed` (`invalid_input`, HITL-043), `agentry.hitl.invalid_edit` (`invalid_input`, HITL-063), `agentry.hitl.unknown_action` (`not_found`, a pending action ID not in the open escalation).
- HITL-061: `tool.call` events carry the `provenances` and `labels` of their arguments (CORE-151): `model` for model-proposed arguments, `reviewer` after an edit. All `beforeToolCall` hooks run on edited arguments, including one that escalated before; stage 7 then does not escalate again.
- HITL-072: `escalation.resolved` is the first event of the resume run after `run.started`, before any model or tool work.
- HITL-011: a `content` action's `contentRef` is a blob of media type `application/json` holding the parts under review as a JSON array. At `afterToolCall`, `tool.result` is appended only once the action is decided (stage 11 follows stage 10). `allowedDecisions` are listed in the order approve, reject, edit, confirm; reviewer `rules` in layer order (bundles in stack order, then the persona); `listPendingEscalations` returns escalations by `createdAt`, oldest first. The approval reason code reflects the effective approval, whether it came from the tool or a sensitivity policy (TOOL-035).
- HITL-082, HITL-090: a TTL or lease has elapsed when the current time is equal to or later than its expiry (as CORE-040/041). The further `idleTtl` after expiry rejections is measured from the `suspendedTtl` expiry time. HITL-100 excludes an escalation whose `suspendedTtl` has elapsed even when, under `onExpiry: reject`, its session is still `suspended`.
