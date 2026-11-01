# Design notes — Human-in-the-loop: escalations and decisions

**Status:** Settled 2026-10-31 · **Date:** 2026-10-31
**Feeds:** Area 6 (Human-in-the-loop); `domain.md` amendment (Escalation and Decision are provisional)
**Related:** Area 1 (session states, CORE-053 idempotent resume), Area 4 (TOOL-033, 036, 062), Area 5 (HOOK-033/034, taint rule, approval rules), ADR-0004 (session as unit of durability), ADR-0014 (reviewers as principals)

> Non-normative working notes. Nothing here is binding until it appears in the Area 6 spec and conformance fixtures.

---

## 1. Position

Several mechanisms already escalate. This note defines what an escalation **contains**, who may **decide** it, what decisions **do**, and what happens when nobody answers. agentry does not deliver notifications or host a review UI: it records escalations and accepts decisions. Routing, paging, and review screens belong to the host or its workflow engine (ADR-0004).

## 2. What escalates

| Source | Raised by |
|---|---|
| `taint` | Taint rule outcome `escalate` (HOOK-122) |
| `approval` | Effective approval `always`, or `policy` with a matching rule (TOOL-035, HOOK-131) |
| `hook` | A hook result `escalate` at any point that permits it (HOOK-033) |
| `recovery` | A non-idempotent mutating call with unknown outcome (TOOL-062) |

## 3. The escalation record

An escalation is created when a session suspends. It contains:

- ID (UUIDv7), session, run, turn, step, tenant, snapshot hash
- **Source** and **reason code**
- One or more **pending actions**, each with:
  - its kind: a tool call (tool, arguments), content at a hook point (the content), or a recovery check (the call whose outcome is unknown)
  - the decisions it allows (§5)
- The **provenances that tainted the session** (HOOK-126), when relevant
- The **reviewer requirements** that apply (§4)
- Created time and expiry time (from `suspendedTtl`)

The escalation is emitted in `escalation.raised` and stays retrievable while the session is `suspended`.

## 4. Reviewers

- A reviewer is a principal (ADR-0014), authenticated by the host, recorded with every decision. A reviewer never replaces the session principal.
- **Reviewer rules** (CEL) declared in policy bundles or personas, per escalation source, decide who may review: e.g. `"clinician" in reviewer.roles && reviewer.assurance == "multi_factor"`.
- See H1 on self-approval and H5 on multiple approvers.

## 5. Decisions

| Decision | Allowed for | Effect |
|---|---|---|
| `approve` | Tool calls, hook content, taint | Processing continues at the next stage (TOOL-036) or next hook (HOOK-034) |
| `reject` | Tool calls, hook content, taint | Tool call: the model receives a `policy` error and the turn continues. Content at `sessionStart`, `beforeModelCall`, `afterModelCall`, or `beforeResponse`: the run ends `blocked` with the fallback message |
| `edit` | Tool calls; content at `beforeResponse` | The reviewer supplies replacement arguments or response, which are validated, then processing continues as if approved |
| `confirm` | Recovery checks | Reviewer states the call `succeeded` (with output if known) or `failed`; the outcome is recorded and delivered to the model |

- Every decision has its own ID. Applying the same decision ID twice returns the original outcome (CORE-053).
- Decisions are immutable and audited: reviewer, decision, timestamp, snapshot hash, and for `edit`, the before and after.
- `resume()` carries the decisions; the run continues only when **every** pending action in the escalation has a decision.

## 6. Decisions (settled 2026-10-31)

- **H1 — Self-approval:** Forbidden by default. A policy bundle may allow it per escalation source, never for `taint` or `recovery`.
- **H2 — Edited content's trust:** New provenance `reviewer`, trusted. Edits pass argument validation and the assurance check, but not the taint rule.
- **H3 — Grouping:** One escalation per step, with one pending action per escalated call, each decided individually.
- **H4 — Expiry:** Never auto-approve. Default: session closes `expired`. A profile may set `onExpiry: reject`.
- **H5 — Multiple approvers:** Optional `requiredApprovals` (default 1), from distinct reviewers; any single `reject` rejects.
- **H6 — Reviewer view:** Escalation record plus pending content, each part redacted unless the reviewer satisfies that label's optional `reviewerRule`.
- **H7 — Finding pending escalations:** `escalation.raised` events plus a tenant-scoped `listPendingEscalations` operation. No notification transport.

## 7. Candidate domain concepts (for `domain.md` amendment)

Escalation (finalised) · Escalation source · Pending action · Decision (finalised) · Decision type · Reviewer rule · Required approvals · Reviewer view · Expiry action

## 8. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] `Escalation`, `PendingAction`, `Decision`
- [ ] Reviewer rule and `requiredApprovals` declarations
- [ ] `onExpiry` profile field

Fixtures:
- [ ] Each escalation source produces a correct record
- [ ] Approve, reject, edit, confirm — each with correct continuation
- [ ] Reject at `beforeResponse` → `blocked` with fallback
- [ ] Edited arguments validated; invalid edit rejected
- [ ] Recovery `confirm: succeeded` delivers recorded output; no re-dispatch
- [ ] Partial decisions → `resume()` rejected until all actions decided
- [ ] Replayed decision ID → original outcome
- [ ] Reviewer failing the reviewer rule → decision refused
- [ ] Self-approval refused by default
- [ ] Two required approvals: one approval insufficient; any reject rejects
- [ ] Expiry → `closed (expired)`; with `onExpiry: reject` → run continues with rejections
- [ ] Reviewer view redacts labels the reviewer is not cleared for
- [ ] `listPendingEscalations` returns only the caller's tenant
