# Conformance suite

Data-only test cases every agentry implementation must pass (Area 11). An implementation conforms to a contract version if, and only if, it passes every fixture it does not legitimately skip (EVAL-023).

## Layout

| Path | Contents |
|---|---|
| `schema/fixture.yaml` | Format of a conformance fixture (EVAL-001–004) |
| `schema/cel-fixture.yaml` | Format of a CEL rule fixture (EVAL-005) |
| `shared/baseline/` | Configuration set most fixtures start from |
| `core/` | Area 1 fixtures |
| `config/` | Area 2–3 fixtures |
| `tools/` | Area 4 fixtures |
| `hooks/` | Area 5 fixtures |
| `hitl/` | Area 6 fixtures |
| `context/` | Area 7 fixtures |
| `orchestration/` | Area 8 fixtures |
| `providers/` | Area 9 fixtures (harness-level, on scripted providers) |
| `adapters/` | Area 9 provider adapter cases (format `schema/adapter-case.yaml`) and recorded vendor transcripts |
| `cel/` | CEL rule fixtures (EVAL-005, HOOK-110–115) |
| `coverage.yaml` | Which areas have complete fixtures, and therefore enforced coverage |

## Writing a fixture

A fixture has three parts:

1. **`setup`** — virtual clock and ID seed, configuration (`base` plus overrides), tenants and principals, registered native handlers, scripted provider responses, stubs (native tools, MCP servers, HTTP endpoints, remote hooks), initial port contents, implementation limits.
2. **`script`** — ordered steps: host actions (`run`, `resume`, `decide`, `close`, `cancel`, `getReviewerView`, `listPendingEscalations`), configuration loads, clock advances, crashes, restarts, abandoned streams, concurrent actions.
3. **`expect`** — event patterns per session, session states, step outcomes, captured provider requests and stub calls, port contents, and content that must never be persisted.

A step's captures are processed in order, so a capture may use `session:` with a placeholder bound by an earlier capture of the same step (e.g. a child session). Placeholders (`$session`, `$run1`) bind on first match in `expect`, or through a step's `capture`, and must match consistently: a placeholder binds the whole value at its first match (scalar, object or array), and every later occurrence must equal that value exactly — deep equality, not the partial matching used for objects written out in an expectation. A placeholder used in a step must be captured by an earlier step. Placeholders may be map keys (e.g. an idempotency key under `ports.idempotencyStore`). `expect` is evaluated in document order, depth-first; a placeholder key must be bound (earlier in document order, or by a capture) before a matcher such as `$absent` is applied to the value under it.

Matchers: `{"$any": true}`, `{"$absent": true}`, `{"$regex": "..."}`, `{"$len": n}`, `{"$contains": [...]}` (each item matches a distinct element), `{"$not": m}`, `{"$every": m}`, `{"$gte": n}`, `{"$lte": n}`, `{"$all": [m1, m2]}`, and `{"$count": {"of": m, "equals"|"gte"|"lte": n}}`, which counts the array elements matching `m`. In adapter cases only, `{"$selfProvider": true}` stands for the adapter's declared provider ID. Write "no element matches" and "exactly one matches" with `$count`, never as `$not` around `$contains`. Matcher names are reserved and are never placeholders; any other `$`-key must be a placeholder.

### Execution model

- **Events are persisted when emitted.** At any point, including a crash point, every event emitted before it is in the event log.
- **Virtual clock.** Time advances only through `clock` steps, except that when every piece of pending work is waiting on a timer (a stub's `delayMs`, a timeout, a lease), the runner advances the virtual clock to the earliest such timer (discrete-event simulation). `startAfter` is evaluated before any automatic advance.

### Setup

- **`handlers`** — native handlers. By default the runner registers a stub handler for every `native` binding, except names beginning `unregistered.`, which are never registered (a binding naming one is unresolved, TOOL-010). A native tool with no `stubs.tools` entry gets the default stub, which records its calls and returns `ok` with output `{}` on every call. Set `handlers` only to restrict registration.
- **`stubs.tools.<toolId>`** — behaviours, consumed in order, one per call (a retry is a call). Each key must be a native-bound tool ID in some configuration the fixture loads. A call after a behaviour list has run out fails the test (this includes an empty list).
- **`stubs.mcpServers.<serverId>`** — `{ tools: { <toolName>: { inputSchema, annotations, behaviours } }, changes: [{ afterCalls: n, tools: {...} }] }`. A change re-advertises the named tools once the server has received `n` calls in all (TOOL-092).
- **`stubs.httpEndpoints.<endpointId>.<operationId>`** — behaviours of that operation. Recorded `arguments` are the tool's arguments.
- **`stubs.remoteHooks.<remoteHookId>`** and **`stubs.nativeHooks.<hookId>`** — hook behaviours, one per invocation: a `HookResult` (`answer`, or its fields given directly), `raw` (a verbatim response body that need not be a valid `HookResult`), `error`, or `hang: true`; `delayMs` delays an answer. A registered native hook with no entry answers `continue`. Each invocation is recorded with `arguments` = the `HookRequest`.
- **`stubs.vectorStores.<sourceId>`** — one behaviour per query: the `results` an unfiltering backend returns (`{id, text, tenant, labels?, access?}`), which the implementation's vector store port filters by tenant and access (PORT-080), or `error`. Queries are recorded as `vectorStore/<sourceId>` stub calls with `arguments: { tenant, principal: { subject, tenant, roles }, text, limit }`.
- **Token counting** — scripted adapters count context tokens deterministically (PROV-045): one per word of a text part, `tokenCounting.nonTextPart` (default 10) per other part, nothing for messages, roles or tool definitions. With `capabilities.contextLimit` and `maxOutputTokens`, this makes compaction and overflow exact. Unless set, `contextLimit` is 1,000,000 and `maxOutputTokens` 4,096.
- **Model hooks** call their model through the scripted provider of their `source.model.provider`, consuming that provider's responses in order like any other call to it; give a model hook its own provider so its responses do not interleave with the session's. The model's answer is a `structured` part whose `value` is the `HookResult`, or a single text part holding it as JSON. These calls appear in `expect.providerRequests`.
- **Behaviours** — exactly one of `ok`, `error` or `hang: true`; `ok` and `error` may take `delayMs`. A delayed or hanging stub honours cancellation (stops without its scripted result, records `cancelled: true`) unless `ignoreCancel: true`.
- **`limits`** — `inlinePayloadBytes` (blob threshold, TOOL-072) and `leaseTtl` (run lease, ISO 8601, default `PT5M`).

### Steps

- **`crash: { at, session }`** arms a crash for the next action step on that session. The action runs until the named point, where the implementation stops abruptly (in-process state lost, ports kept, no outcome to the host); its own `expect` is not checked and may be omitted. Points:
  - `after_started_record` — started record stored; not dispatched;
  - `after_dispatch` — the stub ran (its behaviour is consumed, its side effect happened) but the result never reached the implementation; the stub-call record has `completed: false`;
  - `after_outcome_recorded` — outcome in the idempotency store, before `tool.result` is appended;
  - `after_event_append` — immediately after the event-log append that contains the next `tool.call` event; checkpoint not saved.
  - `after_model_request` — immediately after the next `model.request` is appended, before the provider answers; no response consumed, no tool call in flight.

  The crashed action must be followed, later in the script, by a `restart` step before the next action step.
- **Recovery** (HITL-091 as amended 2026-11-01): an orphaned run that continues keeps its `runId` and emits no new `run.started`. The host call that triggered recovery then runs its own run and receives its own outcome, which its step's `expect` matches.
- **Decisions** in `resume`/`decide`: `{ decisionId, pendingActionId, type: approve|reject|edit|confirm, replacement?, outcome?: succeeded|failed, output? }`. `edit` needs `replacement`; `confirm` needs `outcome`, with `output` the stated output of a successful call. The escalation is the session's open one; the reviewer is the step's `reviewer`. `getReviewerView` (step `session`, `tenant`, `reviewer`) and `listPendingEscalations` (step `tenant`) return their result to the step's `expect.view` and `expect.escalations`.

### Record shapes

- **Stub calls** (`expect.stubCalls`), keyed by native tool ID, `<serverId>/<toolName>`, `<endpointId>/<operationId>`, or remote hook ID: `{ arguments, context: { sessionId, runId, principal, idempotencyKey, deadline, traceContext }, cancelled, completed }`; `arguments` are the tool's arguments (HTTP stubs included), and `completed` is whether the stub's result reached the implementation. Remote and native hook invocations record `{ arguments }`, the `HookRequest` (`schemas/core/v1/hook.yaml`), keyed by remote hook ID or hook ID.
- **Vector store queries** (`expect.stubCalls.vectorStore/<sourceId>`): `{ arguments: { tenant, principal: { subject, tenant, roles }, text, limit } }`.
- **Provider requests** (`expect.providerRequests`): `{ provider, model, messages, tools: [{ name, description, input }], outputSchema, params, singleToolCall }`; a tool's `name` is its tool ID. A step's tool results are sent as ONE message with role `tool` holding all its `tool_result` parts in request order (TOOL-032).
- **Ports** (`expect.ports`, keyed by port name, then tenant):
  - `eventLog: {t1: {<sessionId>: [events]}}`;
  - `idempotencyStore: {t1: {<key>: { state: started|completed, outcome, childSessionId? }}}`;
  - `auditLog: {t1: [{ timestamp, tenant, sessionId, principalRef, snapshotHash, type, reviewer?, eventIds, details }]}`, with `type` one of `hook_decision`, `policy_decision`, `escalation`, `decision`, `tool_call` (details `{ callId, tool, arguments, outcome }`) (PORT-071);
  - `blobStore: {t1: [{ id, hash, mediaType, size, data }]}`;
  - `checkpointStore: {t1: {<sessionId>: checkpoint}}`, with the PORT-030 fields `state`, `principalRef`, `tenant`, `persona`, `snapshotHash`, `taint`, `budget`, `counters`, `reasoning`, `escalation`, `heldResults`, `lease`, `parentSessionId`, `childSessionIds` (also used by `sessions.*.checkpoint`).

Rules:

- Synthetic data only (EVAL-003).
- Assert only what the listed requirements need (EVAL-004).
- Every fixture lists the requirement IDs it verifies; spec CI checks coverage (EVAL-010).
