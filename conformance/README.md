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
| `coverage.yaml` | Which areas have complete fixtures, and therefore enforced coverage |

## Writing a fixture

A fixture has three parts:

1. **`setup`** — virtual clock and ID seed, configuration (`base` plus overrides), tenants and principals, registered native handlers, scripted provider responses, stubs (native tools, MCP servers, HTTP endpoints, remote hooks), initial port contents, implementation limits.
2. **`script`** — ordered steps: host actions (`run`, `resume`, `decide`, `close`, `cancel`), configuration loads, clock advances, crashes, restarts, abandoned streams, concurrent actions.
3. **`expect`** — event patterns per session, session states, step outcomes, captured provider requests and stub calls, port contents, and content that must never be persisted.

Placeholders (`$session`, `$run1`) bind on first match in `expect`, or through a step's `capture`, and must match consistently. A placeholder used in a step must be captured by an earlier step.

Matchers: `{"$any": true}`, `{"$absent": true}`, `{"$regex": "..."}`, `{"$len": n}`, `{"$contains": [...]}` (each item matches a distinct element), `{"$not": m}`, `{"$every": m}`, `{"$gte": n}`, `{"$lte": n}`, `{"$all": [m1, m2]}`, and `{"$count": {"of": m, "equals"|"gte"|"lte": n}}`, which counts the array elements matching `m`. Write "no element matches" and "exactly one matches" with `$count`, never as `$not` around `$contains`. Matcher names are reserved and are never placeholders.

### Setup

- **`handlers`** — native handlers. By default the runner registers a stub handler for every `native` binding, except names beginning `unregistered.`, which are never registered (a binding naming one is unresolved, TOOL-010). A native tool with no `stubs.tools` entry gets a stub that records its calls and returns `ok` with an empty output object. Set `handlers` only to restrict registration.
- **`stubs.tools.<toolId>`** — behaviours, consumed in order, one per call (a retry is a call).
- **`stubs.mcpServers.<serverId>`** — `{ tools: { <toolName>: { inputSchema, annotations, behaviours } }, changes: [{ afterCalls: n, tools: {...} }] }`. A change re-advertises the named tools once the server has received `n` calls in all (TOOL-092).
- **`stubs.httpEndpoints.<endpointId>.<operationId>`** — behaviours of that operation.
- **Behaviours** — `ok` or `error`, optionally `delayMs` or `hang`. A delayed or hanging stub honours cancellation (stops without its scripted result, records `cancelled: true`) unless `ignoreCancel: true`.
- **`limits`** — `inlinePayloadBytes` (blob threshold, TOOL-072) and `leaseTtl` (run lease, ISO 8601, default `PT5M`).

### Steps

- **`crash: { at, session }`** arms a crash for the next action step on that session. The action runs until the named point, where the implementation stops abruptly (in-process state lost, ports kept, no outcome to the host); its own `expect` is not checked and may be omitted. Points: `after_started_record`, `after_dispatch`, `after_outcome_recorded` (outcome in the idempotency store, before `tool.result` is appended), `after_event_append`. A `restart` step follows.
- **Decisions** in `resume`/`decide`: `{ decisionId, pendingActionId, type: approve|reject|edit|confirm, replacement?, outcome?: succeeded|failed, output? }`. `edit` needs `replacement`; `confirm` needs `outcome`, with `output` the stated output of a successful call. The escalation is the session's open one; the reviewer is the step's `reviewer`.

### Record shapes

- **Stub calls** (`expect.stubCalls`), keyed by native tool ID, `<serverId>/<toolName>`, `<endpointId>/<operationId>`, or remote hook ID: `{ arguments, context: { sessionId, runId, principal, idempotencyKey, deadline, traceContext }, cancelled, completed }`. Remote hook calls record `{ arguments }` (the hook request).
- **Provider requests** (`expect.providerRequests`): `{ provider, model, messages, tools: [{ name, description, input }], outputSchema }`; a tool's `name` is its tool ID.
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
