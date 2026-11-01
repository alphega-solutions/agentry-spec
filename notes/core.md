# Design notes — Core model: sessions, events, stop reasons, errors

**Status:** Settled 2026-10-31 · **Date:** 2026-10-31
**Feeds:** Phase 1 (`domain.md` concepts) and Area 1 (Core model)
**Related:** all settled notes — `tools.md`, `hooks.md`, `security.md`, `config.md`

> Non-normative working notes. Nothing here is binding until it appears in `domain.md`, the Area 1 spec, and conformance fixtures.

---

## 1. Position

Every other area refers to sessions, events, and errors. This note fixes their shape so the rest of the spec has one vocabulary. It follows principle 7 from `intent.md`: **the session is the unit of durability**.

## 2. Structure

| Concept | What it is |
|---|---|
| **Session** | A durable conversation between one principal and one persona, pinned to one configuration snapshot. Holds history, taint, and checkpoints. |
| **Run** | One call to `run()` or `resume()`. Produces one event stream that ends with a run end reason. A session usually spans several runs. |
| **Turn** | One principal input and the agent's work until it responds or suspends. |
| **Step** | One model call plus the tool calls that call requested. A turn contains one or more steps. |
| **Event** | One immutable record of something that happened, in strict order within the session. |

A session is pinned to its **principal**, **tenant**, **persona**, and **snapshot hash** at creation. None of these change for the life of the session.

## 3. Session states

| State | Meaning | Leaves by |
|---|---|---|
| `active` | A run is in progress | Run ends → `idle`, `suspended`, or `closed` |
| `idle` | Waiting for the principal's next input | `run()` with new input → `active`; expiry → `closed` |
| `suspended` | Waiting for a human decision (escalation) | `resume()` with a decision → `active`; expiry → `closed` |
| `closed` | Finished; terminal. Reason: `completed`, `cancelled`, `failed`, or `expired` | — |

Rules:
- **One active run per session.** A second concurrent `run()` or `resume()` fails with a `conflict` error. This is enforced through the checkpoint's version (optimistic concurrency).
- `resume()` with a decision ID that was already applied is a no-op that returns the original outcome (idempotent).
- Idle and suspended sessions expire after a TTL set in the harness profile.

## 4. Event envelope

Every persisted event carries the same envelope:

| Field | Purpose |
|---|---|
| `schemaVersion` | Contract version |
| `eventId` | Unique ID |
| `sessionId`, `runId` | Where it belongs |
| `seq` | Strictly increasing per session, no gaps — the ordering authority |
| `turn`, `step` | Position within the session |
| `type` | Event type (below) |
| `timestamp` | RFC 3339 UTC; informational only, never used for ordering |
| `tenantId`, `principalRef` | Isolation and attribution (a reference, never the full principal) |
| `snapshotHash` | Configuration in force |
| `traceContext` | W3C trace and span IDs |
| `provenance`, `sensitivity` | On events that carry content |
| `payload` | Type-specific body |
| `extensions` | Vendor or adapter data |

Ephemeral `model.delta` events (per Q5) carry the envelope but no `seq`, and are never persisted.

## 5. Event catalog (draft)

| Group | Types |
|---|---|
| Session | `session.created`, `session.closed` |
| Run | `run.started`, `run.ended` |
| Turn | `turn.started`, `turn.completed` |
| Model | `model.request`, `model.response`, `model.delta` (ephemeral) |
| Tool | `tool.call`, `tool.result` |
| Governance | `hook.decision`, `policy.decision` (taint rule, assurance check, scope check) |
| Durability | `checkpoint.saved` |
| Human-in-the-loop | `escalation.raised`, `escalation.resolved` |
| Error | `error` |

The catalog is closed in the core: new types require a spec change. Adapters add data through `extensions`, not new types.

## 6. Run end reasons

Every run ends with exactly one reason on `run.ended`:

| Reason | Session goes to | Cause |
|---|---|---|
| `responded` | `idle` | The turn produced a response |
| `escalated` | `suspended` | A hook, policy decision, or tool approval requires a human |
| `blocked` | `idle` | An output guardrail blocked the response; the persona's fallback message is returned |
| `step_limit` | `idle` | Steps per turn exceeded the profile limit |
| `budget_exhausted` | `idle` | Token or cost budget reached |
| `timeout` | `idle` | Wall-clock limit reached |
| `cancelled` | `closed` (`cancelled`) | `cancel()` called or the stream was abandoned |
| `failed` | `closed` (`failed`) | Unrecoverable error |

### Where a `block` lands

| Hook point | Effect of `block` |
|---|---|
| `sessionStart`, `beforeModelCall` | Run ends `blocked`; no model call is made |
| `afterModelCall` | The model output is discarded; run ends `blocked` |
| `beforeToolCall` | The tool is not called; the model receives a `policy` error as the tool result and may continue |
| `afterToolCall` | The result is withheld; the model receives a `policy` error as the tool result |
| `beforeResponse` | Run ends `blocked`; the fallback message is returned |

## 7. Error model

One error shape is used by tools, hooks, providers, storage ports, and the harness:

| Field | Purpose |
|---|---|
| `code` | Namespaced, stable identifier, e.g. `agentry.tool.timeout`, `io.alphega.scheduling.slot_taken` |
| `category` | Drives behaviour (below) |
| `retryable` | Whether the harness may retry |
| `source` | `tool`, `hook`, `provider`, `port`, `harness`, `config` |
| `message` | Safe, human-readable text. Never contains sensitive content |
| `details` | Structured data, subject to the same sensitivity labels and redaction as any content |

Categories (extends the tool categories from `notes/tools.md`):

| Category | Meaning | Typical handling |
|---|---|---|
| `invalid_input` | Bad arguments or request | Returned to the model to correct |
| `unauthorized` | Principal lacks rights, or assurance too low | Not retried; may escalate |
| `policy` | Blocked by a guardrail or the taint rule | Not retried; see block table |
| `limit` | Budget, step limit, or timeout reached | Ends the run with the matching reason |
| `unavailable` | Provider, port, or tool temporarily down | Retried per profile, then `fatal` |
| `conflict` | Concurrent run, or checkpoint version mismatch | Returned to the caller |
| `not_found` | Missing session, snapshot, or resource (including wrong tenant) | Returned to the caller |
| `configuration` | Invalid configuration | Load-time only; nothing loads |
| `cancelled` | Work stopped by cancellation | Ends the run `cancelled` |
| `fatal` | Unrecoverable | Ends the run `failed` |

## 8. Decisions (settled 2026-10-31)

- **K1 — ID format:** UUIDv7 for session, run, and event IDs.
- **K2 — Fallback message on `blocked`:** Declared in the persona, with a policy-bundle default. Never generated by the model.
- **K3 — Large or sensitive payloads:** Inline up to a size limit, with redaction per sensitivity policy; larger payloads are stored in the BlobStore and referenced.
- **K4 — Session TTL defaults:** No spec default. Harness profiles must set `idleTtl` and `suspendedTtl` explicitly.
- **K5 — Multi-turn history limits:** Left to the context manager (Area 7). The core guarantees only that events are complete and ordered.

## 9. Candidate domain concepts (for `domain.md`)

Session · Session state · Run · Run end reason · Turn · Step · Event · Event envelope · Sequence number · Fallback message · Error · Error category · Error code · Session TTL

## 10. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] Event envelope
- [ ] Payload schema per event type
- [ ] `Error`
- [ ] Session state and run end reason enums

Fixtures:
- [ ] Single turn, no tools → `responded`, session `idle`
- [ ] Multi-step turn with tool calls → correct `turn`/`step`/`seq` numbering
- [ ] `seq` strictly increasing with no gaps across several runs
- [ ] Concurrent `run()` on an active session → `conflict`
- [ ] `resume()` replayed with the same decision ID → original outcome, no new work
- [ ] Each run end reason, with the correct resulting session state
- [ ] `block` at each hook point behaves per the block table
- [ ] Error `message` never contains labelled sensitive content
- [ ] Idle and suspended sessions expire per TTL → `closed` (`expired`)
- [ ] `model.delta` events have no `seq` and are absent from persisted traces
