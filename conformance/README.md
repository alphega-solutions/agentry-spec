# Conformance suite

Data-only test cases every agentry implementation must pass (Area 11). An implementation conforms to a contract version if, and only if, it passes every fixture it does not legitimately skip (EVAL-023).

## Layout

| Path | Contents |
|---|---|
| `schema/fixture.yaml` | Format of a conformance fixture (EVAL-001–004) |
| `schema/cel-fixture.yaml` | Format of a CEL rule fixture (EVAL-005) |
| `shared/baseline/` | Configuration set most fixtures start from |
| `core/` | Area 1 fixtures |
| `coverage.yaml` | Which areas have complete fixtures, and therefore enforced coverage |

## Writing a fixture

A fixture has three parts:

1. **`setup`** — virtual clock and ID seed, configuration (`base` plus overrides), tenants and principals, scripted provider responses, tool stubs, initial port contents.
2. **`script`** — ordered steps: host actions (`run`, `resume`, `decide`, `close`, `cancel`), configuration loads, clock advances, crashes, restarts, abandoned streams, concurrent actions.
3. **`expect`** — event patterns per session, session states, step outcomes, captured provider requests and stub calls, port contents, and content that must never be persisted.

Placeholders (`$session`, `$run1`) bind on first match and must match consistently. Matchers: `{"$any": true}`, `{"$absent": true}`, `{"$regex": "..."}`, `{"$len": n}`, `{"$contains": [...]}`.

Rules:

- Synthetic data only (EVAL-003).
- Assert only what the listed requirements need (EVAL-004).
- Every fixture lists the requirement IDs it verifies; spec CI checks coverage (EVAL-010).
