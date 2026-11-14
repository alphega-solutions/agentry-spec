# ADR-0020: One shared conformance runner; implementations provide a driver

**Status:** Proposed 2026-11-14 · **Date:** 2026-11-14 · **Source:** post-Phase 4 review (runner matching ambiguity, EVAL-004 amendment 2026-11-14); Phase 5 plan (Python, Node.js and Java implementations); Area 11 §4–5

## Context
EVAL-020 requires each implementation to provide its own conformance runner. With three implementations, that means three fixture loaders, three expectation matchers and three script engines. Each script engine must handle concurrency, crash and restart, the virtual clock, stubs and scripted providers. Each must also interpret the fixture format identically.

The review already found one way they would diverge: greedy versus searching assignment in unordered matching (#23). With per-implementation runners, a conformance failure may come from the runner as easily as from the harness, and two runners can judge the same implementation differently.

The spec repository now has a reference matcher (`tools/matcher.py`). The lead implementation is Python.

## Decision
- **One runner.** The spec repository provides the conformance runner: `tools/runner/`, in Python, built on the reference matcher. It loads fixtures, port cases and adapter cases for a contract version, executes their scripts, matches every expectation, and writes the reports (EVAL-021) and the conformance claim (EVAL-023).
- **Drivers.** Each implementation provides a **driver**: a process that exposes its harness, its in-memory port adapters and its test doubles (EVAL-030–035) through the **driver protocol**. A driver interprets nothing: it executes requests and reports observations.
- **The driver protocol** is JSON-RPC 2.0 over stdio, specified by `conformance/schema/driver.yaml` and versioned with the contract (ADR-0002). It covers:
  - **Setup:** configuration loads (including overlays and loads expected to fail); tenants and principals; scripted providers; stubs for tools, MCP servers, HTTP endpoints, remote and native hooks and vector stores; seeded port records; clock, ID seed and limits.
  - **Actions:** every host action in the fixture format (`run`, `resume`, `decide`, `close`, `cancel`, `getReviewerView`, `listPendingEscalations`, `exportBundle`, `replay`, `convert`, `evalRun`). Requests are asynchronous with IDs, so `concurrently`, `startAfter` and `separateProcesses` are expressible.
  - **Control:**
    - arm a crash at a named point (the driver discards the harness instance there);
    - `restart`: a new harness instance over the same port objects (EVAL-035);
    - clock set and advance; retention runs; abandoned streams;
    - two harness instances sharing ports.
  - **Observation:** events per session, port contents, stub calls, provider requests, delivered output, and each step's outcome.
  - **Port and adapter cases:** port operations invoked directly on a named port adapter, and provider adapter requests. Any adapter, including a production one (PORT-001, PORT-009), is tested by the same runner.
- **Matching and judgement live only in the runner.** Drivers never evaluate expectations.
- **The claim.** A conformance claim is the shared runner's report for a driver, naming the contract version, the runner version, the driver and the declared unsupported features (EVAL-022, EVAL-023). Native runners are permitted for development, but they are not the basis of a claim.
- **Cross-implementation replay.** The runner may export a bundle through one driver and replay it through another in one run, which verifies EVAL-026 directly.
- **Spec changes:**
  - EVAL-020 becomes: implementations **MUST** provide a driver conforming to the driver protocol; the spec repository provides the runner.
  - EVAL-021 and EVAL-023 refer to the shared runner's report.
  - EVAL-035 is satisfied through the protocol's crash and restart control.
  - `conformance/coverage.yaml` `verifiedElsewhere` entries for EVAL-020/021 are updated to match.
- **Protocol conformance.** The repository ships a **fake driver**, which answers from golden bundles and canned observations, and runner self-tests against it, so the runner and protocol are tested before any harness exists.

## Consequences
- **One interpretation.** Every implementation is judged by the same loader, script engine and matcher. Any difference in results is a difference in the harness.
- **Small drivers.** Node.js and Java implement a protocol, not the fixture semantics. The test doubles they must build anyway are reused.
- **Format changes in one place.** A fixture-format change is implemented once, in the runner. A protocol change is versioned and announced.
- **Costs.** A protocol schema to design and maintain; a process boundary, adding some seconds to a full run; and the runner becomes a maintained product of the spec repository.
- **Testing production adapters.** Port adapters for production stores (for example the ones in `notes/deployment-agentcore.md`) are tested by the same runner through a driver that binds them (PORT-001).

## Alternatives considered
- **A runner per implementation (the current EVAL-020).** No protocol, fully in-process, idiomatic per language. But it means three loaders, matchers and script engines to keep identical, and runner bugs indistinguishable from harness bugs.
- **Per-language runners ported from the reference matcher.** Less matcher divergence, but three script engines remain: concurrency, crashes and the clock, where the subtle bugs live.
- **A shared runner over an in-process FFI or embedded language.** Avoids a process boundary, but ties the runner to each language's runtime and build. Stdio JSON-RPC works the same for Python, Node.js and Java.
