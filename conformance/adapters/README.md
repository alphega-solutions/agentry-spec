# Provider adapter cases

Vendor-neutral fixtures for the provider adapter contract (PROV §11, EVAL-011). Format: [`../schema/adapter-case.yaml`](../schema/adapter-case.yaml).

| Path | Contents |
|---|---|
| `cases/` | One case per file: a harness request, a provider-side `condition`, and what the adapter must return and send, in agentry terms |
| `transcripts/<adapter>/<case id>.yaml` | Per native adapter: the recorded wire-level response for the case's condition and matchers over the wire request (EVAL-036) |

Every adapter — native, framework-wrapping (PROV-009) or scripted (EVAL-031) — must pass every case. Harness-level provider behaviour (routing, failover, usage accounting, cost, configuration) is tested by the ordinary fixtures in `../providers/`, which run on scripted providers.

**Status:** transcripts are recorded from each native adapter's real vendor endpoint and published with the suite before the first release (Phase 5). None is published yet, so native adapters cannot run the cases until then; the cases themselves are normative now.
