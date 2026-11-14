# Shared conformance runner

The conformance runner for every agentry implementation (ADR-0020, EVAL-020). It runs the fixtures in `conformance/` against an implementation through that implementation's **driver**, which speaks the protocol in [`conformance/schema/driver.yaml`](../../conformance/schema/driver.yaml). It then writes the conformance report (`schemas/eval/v1/conformance-report.yaml`) and JUnit XML.

```
python tools/runner/run.py --driver "<command that starts your driver>" \
    [--fixtures "core/*.yaml" ...] [--report report.json] [--junit report.xml]
```

It exits 0 when no fixture failed. The report's `conforms` (the claim, EVAL-023) is true only for a full-suite run with no failures. Fixture globs are relative to `conformance/`.

| File | Role |
|---|---|
| `run.py` | CLI: discovers fixtures, runs each, writes the report and JUnit |
| `engine.py` | Executes one fixture: configuration resolution, placeholders, actions and scheduling (`startAfter`, discrete-event clock advance), crashes and restarts, captures, step outcomes and every top-level expectation |
| `cases.py` | Executes port cases, provider adapter cases and CEL rule fixtures |
| `client.py` | JSON-RPC 2.0 over the driver's stdio |
| `fake_driver.py` | A test driver that runs no harness and answers `replay` from golden bundles; used by `tools/runner_test.py` |

Expectations are matched by the reference matcher (`tools/matcher.py`).

**Case kinds.** The runner runs every kind of conformance case through the driver:
- **Harness fixtures** (`core/`, `tools/`, `hooks/` and so on): actions, scheduling, crashes, restarts and `abandon` steps.
- **Port cases** (`ports/`): once per port adapter the driver lists in `portAdapters` (`port.call`). It checks `$now`, binds, clock steps, and the implicit `storedRecords` check (every stored record validates against its record schema).
- **Provider adapter cases** (`adapters/cases/`): once per adapter in `providerAdapters` (`adapter.call`), with `$selfProvider`.
- **CEL rule fixtures** (`cel/`): via `cel.evaluate`. Results use a typed encoding, so `3` and `3.0` stay distinct.

Port and adapter results are reported per adapter, as `<case id>@<adapter>`. A driver that offers no adapter for a port or provider case fails that case.
