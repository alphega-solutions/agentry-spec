# ADR-0005: Streaming: step events are core, token deltas optional, buffered by default

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` Q5

## Context
Token streaming improves user experience, but output guardrails can only stop content they see before the user does. In regulated settings, a leak that is merely flagged afterwards is not acceptable.

## Decision
- The **step-level event stream** is core and normative: persisted, traced, and conformance-tested.
- **Token deltas** are an optional `model.delta` event: never persisted, traced, or checkpointed. If emitted, they must concatenate exactly to the final `model.response`.
- **Delivery mode** is set per harness profile:
  - `buffered` (default) — output hooks run on the full response before release.
  - `streamed` — deltas pass through and output hooks are advisory. A profile is invalid if any hook declares it must block output.
- Abandoning a stream maps to `cancel()` and leaves a consistent checkpoint.
- Out of scope: transport (SSE, WebSocket, gRPC), tool-argument streaming, and incremental streaming guardrails. Incremental streaming guardrails are a candidate post-1.0 extension.

## Consequences
- Regulated personas default to safe behaviour; UIs show progress from step events.
- Low-risk personas can stream, with the trade-off declared in configuration.

## Alternatives considered
- **Streaming as the default** — faster perceived response, but guardrails become after-the-fact.
- **Streaming excluded entirely** — safe, but unnecessarily limits low-risk uses.
