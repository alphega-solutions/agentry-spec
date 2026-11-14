# Tools

Spec CI and conformance tooling. Install with `pip install -r tools/requirements.txt` (exact pins). Run each tool from the repository root. CI runs all of them on every pull request (`.github/workflows/spec.yml`).

| Tool | What it does |
|---|---|
| `validate.py` | Validates every schema and every schema example, and every fixture against its format (EVAL-001). It also runs the bespoke checks: placeholders bound before use (EVAL-002), offline URLs (EVAL-024), merge annotations and strictness orders (CFG-030, CFG-031), secret markers (CFG-060, CFG-061), inline configuration, handlers, stub keys, matchers, crashes and concurrency, each invalid example's `repair`, and the code registry: every `agentry.*` code registered, and used in fixtures with its registered category, retryability and source (CORE-192). |
| `coverage.py` | Requirement coverage (EVAL-010). Every normative requirement must be cited by a fixture, or be listed in `conformance/coverage.yaml` as verified elsewhere or pending. |
| `selftest.py` | Negative tests for `validate.py` and `coverage.py`: each check is shown to reject a deliberately broken input. |
| `check_golden.py` | Checks the golden trace bundles in `conformance/golden/` (EVAL-025, EVAL-026): sequence, hashes, blobs, snapshot and audit records. |
| `matcher.py`, `matcher_test.py` | The reference expectation matcher (EVAL-004) and its tests, including a corpus check against the golden bundles. |
| `runner/`, `runner_test.py` | The shared conformance runner (ADR-0020) and its tests. See [`runner/README.md`](runner/README.md). |
| `build.py` | Publishes the YAML schemas as JSON to `dist/`, with resolvable `$id`s (ADR-0001). |
| `common.py` | Shared loading helpers. |
