# Area 8 — Orchestration (delegation)

**Status:** Approved 2026-10-31 · **Contract version:** 0.1.0-draft · **Date:** 2026-10-31
**Sources:** `intent.md` Q4; `domain.md` (approved, incl. amendments); notes `security.md`, `tools.md` (settled); ADR-0004, 0008, 0014; Areas 1–7 and 9 (approved), esp. TOOL-022, TOOL-100–103, CFG-012, HITL-001

---

## 1. Scope

agentry's orchestration is **agent-driven delegation only** (ADR-0004): a persona calls another persona as a tool, through an `agent` binding (Area 4 §9). This area specifies the child session that runs the delegated persona: what it inherits, how its depth, budget, and providers are limited, how its escalations reach a human, how its outcome returns, and how it is cancelled and recovered.

Fixed workflows, sequencing across sessions, timers, and schedules belong to the host's workflow engine (ADR-0004). This area is Tier 3: it builds on settled decisions and has no design note.

## 2. Conventions

As in Area 1 §2. Requirement IDs use the prefix `ORCH-`. The **parent** is the session whose model called the agent tool; the **child** is the session it creates. The **root** is the outermost session. A **delegation chain** is the root and its descendants.

## 3. Creating a child session

- **ORCH-001** Each dispatched call to an `agent`-bound tool **MUST** create a new child session with its own UUIDv7 ID (CORE-001). Child sessions are not reused across calls.
- **ORCH-002** Before the child starts, the parent **MUST** record a started record for the call in the idempotency store, holding the child's session ID, whatever the agent tool's `effect`. Agent-bound tools are therefore idempotent by construction: re-dispatching the call re-attaches to the recorded child rather than creating another (TOOL-062's idempotent branch applies).
- **ORCH-003** The child **MUST** be pinned to the parent's principal, tenant, and snapshot (CORE-012). Its persona is the one referenced by the binding.
- **ORCH-004** The child's `session.created` event **MUST** record the parent session ID, parent run ID, the call's tool `id` and call ID, and the delegation depth. Its trace context **MUST** be a child span of the parent call's span.
- **ORCH-005** The child's harness profile is its persona's `defaultProfile`. A child has no run request, so CFG-100 does not apply.
- **ORCH-006** Host operations (`run()`, `resume()`, `decide()`, `close()`, `cancel()`) on a child session **MUST** be refused with error category `conflict`. Hosts interact only with root sessions.

## 4. What the child sees

- **ORCH-010** The child's first message has role `principal` and contains the agent tool call's arguments, as validated against the tool's `input` schema. The child does not see the parent's history; anything it needs must be in the arguments.
- **ORCH-011** That message **MUST** carry the least-trusted provenance and the union of the labels in the parent's context at the time of the call — not provenance `principal`. *(Amends CORE-120 for child sessions.)*
- **ORCH-012** If the parent is tainted, the child **MUST** start tainted and inherit the parent's tainting provenances (HOOK-121, HOOK-126).
- **ORCH-013** The child's visible tools **MUST** be the intersection of its persona's allowlist and the parent's **visible** tools for the calling step. *(Tightens TOOL-022, which said the parent's runtime scope; a runtime scope can include tools outside the parent's allowlist, and delegation must never widen what is reachable — `domain.md` invariant 11.)*
- **ORCH-014** The child's effective allowed providers **MUST** be the intersection of its own and the parent's (CFG-070, CFG-080).
- **ORCH-015** The child runs the hooks required by the policy bundles, its persona, and its profile, like any session (HOOK-030).
- **ORCH-016** The child's delivery is always `buffered`, regardless of its profile's `deliveryMode`. Its output reaches the parent as a tool result, never as deltas.

## 5. Governance of agent tools

- **ORCH-020** For each agent-bound tool, the implementation **MUST** compute at load time the child's **reachable tools**: the child persona's allowlist, plus, for each agent tool in it, that tool's reachable tools, repeated until no new tools are added (cycles terminate because the set only grows). The agent tool's `effect` **MUST** be `mutating` if any reachable tool is mutating, and its `egress` **MUST** be `true` if any reachable tool is egress. A weaker declaration is a configuration error. *(Extends CFG-042.)*
- **ORCH-021** If an agent tool declares `output`, the child persona **MUST** declare an output schema compatible with it; otherwise configuration is rejected.
- **ORCH-022** An agent tool listed in `trustedTools` is a configuration error. Delegated output is never trusted beyond what the child saw (TOOL-102).
- **ORCH-023** If any layer sets `budget.cost` for the parent, every model reachable through delegation **MUST** be priced (PROV-073).
- **ORCH-024** The agent tool call passes through the full tool pipeline in the parent (Area 4 §6), including the taint rule and approval, before the child is created.

## 6. Limits

### 6.1 Depth

- **ORCH-030** Delegation depth is 0 for the root and increases by 1 per child. A harness profile **MAY** set `delegation.maxDepth` (merge rule `min`, default 2). A child's effective `maxDepth` is the smaller of its own profile's value and its parent's effective `maxDepth`. *(Extends CFG-090.)*
- **ORCH-031** The depth check runs at tool pipeline stage 1 (availability). A call that would create a child deeper than the parent's effective `maxDepth` **MUST** be stopped there with a `policy` error (`agentry.delegation.depth`), emitting a `policy.decision` with an audit record.

### 6.2 Budgets and time

- **ORCH-040** Agent-bound calls within one step **MUST** run one at a time, in request order. Other tool calls in the step may run in parallel. *(Narrows TOOL-032 for agent tools.)*
- **ORCH-041** A child's budget is the smaller of its own profile's budget and the parent's remaining turn budget when the child starts.
- **ORCH-042** Tokens and cost used by the child **MUST** count toward the parent's turn budget as well as the child's own. *(Extends CFG-091 and PROV-071.)* If the parent's budget is exhausted as a result, the parent's run ends `budget_exhausted` after the child returns.
- **ORCH-043** A child's wall-clock limit is the smaller of its own `timeouts.run` and the parent call's remaining deadline.
- **ORCH-044** Time a session spends `suspended` **MUST NOT** count toward any tool call deadline or run timeout in the delegation chain. *(Clarifies TOOL-051.)*
- **ORCH-045** While a child runs, the parent's run lease (HITL-090) **MUST** continue to be renewed.

## 7. Returning to the parent

- **ORCH-050** When the child's run ends for any reason other than `escalated`, the implementation **MUST** close the child session (reason `completed`, or `cancelled`/`failed`/`expired` as applicable) and return its outcome to the parent as the agent tool's result:

| Child run end reason | Parent tool result |
|---|---|
| `responded` | `ok` with the child's final response (its `structured` part if it has an output schema, otherwise its text) |
| `blocked` | Error `policy` (`agentry.delegation.blocked`). The child's fallback message is not used |
| `step_limit`, `budget_exhausted`, `context_limit`, `timeout` | Error `unavailable`, `retryable: false` (`agentry.delegation.limit`) |
| `failed` | Error `unavailable`, `retryable: false` (`agentry.delegation.failed`) |
| `cancelled` | See ORCH-070 |

- **ORCH-051** Error results from delegation (`agentry.delegation.*`) **MUST** be delivered to the parent model as tool results and **MUST NOT** by themselves end the parent run. *(Exception to CORE-191 and TOOL-053, which would otherwise treat a non-retryable `unavailable` as `fatal`.)*
- **ORCH-052** The result **MUST** carry provenance `agent:<persona>`, the least-trusted provenance the child saw, and the union of the labels it saw (TOOL-102). Binary content is returned as blob references (CORE-112).

## 8. Escalations in a delegation chain

- **ORCH-060** When a child suspends with an escalation, every ancestor up to the root **MUST** also checkpoint and suspend, each with its own escalation containing the same pending actions (same IDs), annotated with the chain of child session IDs that leads to the owning session. Each ancestor's run ends `escalated` (HITL-003). *(Extends HITL-001, HITL-002, HITL-003, HITL-010.)*
- **ORCH-061** Each pending action keeps its **original** source (`taint`, `approval`, `hook`, `recovery`) and is marked `delegated: true`. HITL-023's self-approval ban and every source-keyed reviewer rule apply exactly as for a non-delegated action.
- **ORCH-062** Reviewer rules from every session in the chain that owns or mirrors the action **MUST** apply (`union`). The effective `requiredApprovals` is the highest among them (HITL-024).
- **ORCH-063** Decisions are submitted against the root's escalation only; `listPendingEscalations` returns root escalations only (HITL-100). *(Narrows HITL-100.)*
- **ORCH-064** When every pending action is decided, `resume()` on the root **MUST** apply the decisions to the owning child, resume it, and resume each ancestor in turn as its child's result becomes available, recording `escalation.resolved` at each level. If the child raises a new escalation, it propagates per ORCH-060.
- **ORCH-065** The chain's escalation expires at the earliest `suspendedTtl` expiry among its sessions, and uses the strictest `onExpiry` among them (`close` over `reject`). *(Amends CORE-040/041 and HITL-081 for chained sessions.)*
- **ORCH-066** On expiry with `close`, every session in the chain **MUST** close `expired`, from the deepest child to the root. No tool results are written to sessions being closed.

## 9. Cancellation, closing, and recovery

- **ORCH-070** When a parent session or run is cancelled, closed, or expires for any reason, every descendant that is not closed **MUST** first be cancelled, deepest first, and closed `cancelled`. Children never close independently of their parent except by returning (ORCH-050).
- **ORCH-071** Recovery of an orphaned run (HITL-091) **MUST** use the started records (ORCH-002) to find in-flight children and recover them first, deepest first, applying HITL-091 to each, then re-attach the parent call to the child's outcome.

## 10. Recording

- **ORCH-080** A child session's events are its own, in its own sequence (CORE-160). The parent records the delegation as the agent tool's `tool.call` (including the child session ID) and `tool.result`.
- **ORCH-081** An auditor **MUST** be able to navigate from a parent `tool.call` to the child session and back (ORCH-004, ORCH-080).

## 11. Conformance fixtures (to be written in Phase 4)

| Fixture | Requirements |
|---|---|
| Each agent call creates a new child with a UUIDv7 ID | ORCH-001 |
| Started record holds child ID even for a read-only agent tool; re-dispatch re-attaches | ORCH-002 |
| Child pinned to parent's principal, tenant, snapshot | ORCH-003 |
| Child `session.created` links to parent; trace span nested; navigable both ways | ORCH-004, 080, 081 |
| Child uses its persona's default profile | ORCH-005 |
| Host operations on a child → `conflict` | ORCH-006 |
| Child's first message is the arguments, with parent provenance and labels; no parent history | ORCH-010, 011 |
| Tainted parent → tainted child with provenances | ORCH-012 |
| Child tools = own allowlist ∩ parent visible tools; runtime scope cannot widen | ORCH-013 |
| Child providers = own ∩ parent's | ORCH-014 |
| Child runs bundle, persona, profile hooks | ORCH-015 |
| Child buffered even if its profile says streamed | ORCH-016 |
| Agent tool declared `read` or non-egress while reachable tools mutate or send out → rejected; cyclic personas computed correctly | ORCH-020 |
| Agent tool `output` without compatible child output schema → rejected | ORCH-021 |
| Agent tool in `trustedTools` → rejected | ORCH-022 |
| Parent cost budget with unpriced reachable model → rejected | ORCH-023 |
| Agent call subject to taint rule and approval in parent | ORCH-024 |
| Depth beyond limit → stopped at stage 1, `policy.decision` audited; delegation cycle stops at limit | ORCH-030, 031 |
| Two agent calls in one step run sequentially | ORCH-040 |
| Child budget capped by parent's remaining; usage counted in both; parent exhausted after return → `budget_exhausted` | ORCH-041, 042 |
| Child deadline capped by parent's; suspension time excluded | ORCH-043, 044 |
| Parent lease renewed during a long child | ORCH-045 |
| Each child run end reason → parent tool result; child closed; parent run continues on errors | ORCH-050, 051 |
| Child result provenance, labels, blob references | ORCH-052 |
| Child escalation → every ancestor suspends with mirrored actions | ORCH-060 |
| Delegated taint action: self-approval refused; source-keyed rules apply | ORCH-061 |
| Reviewer rules from the whole chain apply | ORCH-062 |
| Only root escalation accepts decisions and is listed | ORCH-063 |
| Root resume cascades down and back up; new child escalation propagates | ORCH-064 |
| Earliest TTL and strictest `onExpiry` in the chain apply | ORCH-065 |
| Chain expiry closes deepest first; no results written | ORCH-066 |
| Parent cancelled, closed, or expired while child suspended → children closed first | ORCH-070 |
| Orphaned parent with in-flight child → child recovered first, parent re-attached | ORCH-071 |

## 12. Additions approved with this spec (2026-10-31)

All rules here are new; this is a Tier 3 area. Rules that amend approved areas are marked.

| ID | Proposed rule |
|---|---|
| ORCH-001, 002 | New child per call; started record for every agent call, making agent tools idempotent by construction |
| ORCH-005, 006 | Child uses its persona's default profile (CFG-100 not applicable); **hosts can only operate on root sessions** |
| ORCH-010, 011 | Child sees only the arguments; **its first message inherits parent provenance, not `principal`** (amends CORE-120) |
| ORCH-012 | Child inherits parent taint |
| ORCH-013 | **Child scope intersects the parent's visible tools** (tightens TOOL-022) |
| ORCH-014 | Child providers intersect the parent's |
| ORCH-016 | Children always buffer (overrides profile `deliveryMode`) |
| ORCH-020–023 | Reachable-tool computation for mutating/egress (extends CFG-042); output-schema compatibility; agent tools never trusted; transitive pricing |
| ORCH-030, 031 | `delegation.maxDepth` (default 2) (extends CFG-090); depth checked at stage 1 and audited |
| ORCH-040 | **Agent calls in one step run sequentially** (narrows TOOL-032) |
| ORCH-041–045 | Child budget and deadline capped by parent; child usage counts toward parent (extends CFG-091, PROV-071); suspension time excluded from deadlines (clarifies TOOL-051); lease renewed |
| ORCH-050, 051 | Child outcome mapping; **delegation errors never end the parent run by themselves** (exception to CORE-191, TOOL-053) |
| ORCH-060–066 | **Escalations mirrored on every ancestor; decisions only at the root**; original sources kept for self-approval and reviewer rules; earliest TTL and strictest `onExpiry` in the chain (amends HITL-001/002/003/010/100, CORE-040/041, HITL-081) |
| ORCH-070, 071 | Closing or cancelling a parent closes descendants first; recovery handles children first (amends CORE-020, HITL-091) |

## Appendix A — Workflow engines (informative)

Hosts interact only with root sessions (ORCH-006), so the integration patterns in Area 6 Appendix A apply unchanged: a delegation chain behaves, from outside, as one session that may suspend for decisions. Deterministic multi-agent pipelines — run persona A, then persona B — belong in the workflow engine as separate root sessions, not in delegation.

## Amendment 2026-11-02 — from Phase 4 (schemas and fixtures)

Schemas: the `session.created` `parent` block and `tool.call` `childSessionId` in `schemas/core/v1/event.yaml`; `delegation.maxDepth` in `schemas/config/v1/harness-profile.yaml`; delegated pending actions (`delegated`, `chain`) in `schemas/core/v1/hitl.yaml`.

**The child's input and output**

- ORCH-010: the child's first message is one `principal`-role message with one `structured` part whose `value` is the validated arguments, carrying the provenance and labels of ORCH-011.
- ORCH-050: for `responded`, the agent tool's `ok` output is the child's `structured` part's `value` when the child persona has an output schema, and otherwise `{ "text": <the response's text parts joined with a newline> }`.
- ORCH-052, HOOK-120: the parent's `tool_result` part has provenance `agent:<persona id>` and the union of the labels the child saw; the `tool.result` event's `provenances` lists `agent:<persona id>` followed by every untrusted provenance the child saw, in order of first entry. The result is **trusted** — it does not taint the parent — only if the child was never tainted; otherwise it taints the parent, whose taint provenances gain `agent:<persona id>` and the child's tainting provenances.

**Host operations and errors**

- ORCH-006: every host operation on a child session — including `getReviewerView` — is refused with `conflict` (`agentry.delegation.child_session`); `listPendingEscalations` never returns a child's escalation (ORCH-063).
- ORCH-031: the depth `policy.decision` has kind `depth`, outcome `block`, and the call's `callId` and `tool`.

**Escalations (ORCH-060–066)**

- A mirrored pending action has the owning session's action ID, `delegated: true` and `chain` (the child session IDs from the nearest child down to the owner), and the record's `expiresAt` is the chain's earliest expiry (ORCH-065). The owner's own escalation is an ordinary one (`delegated` absent).
- Each ancestor's escalation record carries its own `id`, `sessionId`, `runId`, `turn`, `step` and `snapshotHash`; `taintProvenances` are each session's own.
- On an accepted `resume()` of the root, every session in the chain starts a new run in turn — the owner first, then each ancestor as its child's result is ready — and each emits `escalation.resolved` listing the decision IDs applied to the actions it mirrored or owned.

**Ordering**

- ORCH-001, ORCH-080: the parent's `tool.call` for an agent tool, carrying `childSessionId`, is appended before the child's `session.created`. The child's events are in its own sequence (CORE-160) and its session appears under its own ID in every port.
