# Shared conformance runner

The conformance runner for every agentry implementation (ADR-0020, EVAL-020). It runs the fixtures in `conformance/` against an implementation through that implementation's **driver**, which speaks the protocol in [`conformance/schema/driver.yaml`](../../conformance/schema/driver.yaml). It then writes the conformance report (`schemas/eval/v1/conformance-report.yaml`) and JUnit XML.

```
python tools/runner/run.py --driver "<command that starts your driver>" \
    [--fixtures "core/*.yaml" ...] [--report report.json] [--junit report.xml]
```

It exits 0 only when the report conforms (EVAL-023). Fixture globs are relative to `conformance/`.

| File | Role |
|---|---|
| `run.py` | CLI: discovers fixtures, runs each, writes the report and JUnit |
| `engine.py` | Executes one fixture: configuration resolution, placeholders, actions and scheduling (`startAfter`, discrete-event clock advance), crashes and restarts, captures, step outcomes and every top-level expectation |
| `client.py` | JSON-RPC 2.0 over the driver's stdio |
| `fake_driver.py` | A test driver that runs no harness and answers `replay` from golden bundles; used by `tools/runner_test.py` |

Expectations are matched by the reference matcher (`tools/matcher.py`).

**Not yet executed:**
- `abandon` steps: a fixture using one fails with a "not … by this runner yet" message, never a pass.
- Port cases (`conformance/ports/`), provider adapter cases (`conformance/adapters/`) and CEL rule fixtures (`conformance/cel/`) are not discovered yet. The protocol already covers the first two with `port.call` and `adapter.call`. A conformance claim needs them, so the runner does not claim conformance until they run.
