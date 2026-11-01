# ADR-0004: The session is the unit of durability; agentry is not a workflow engine

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` Q4, principle 7

## Context
Multi-agent orchestration tends to grow into a workflow engine (graphs, timers, schedules, compensation). Mature engines already do this well, and building one would roughly double the contract for three implementations.

## Decision
- agentry owns everything **inside** a session: model decisions, tools, hooks, and agent-driven delegation.
- The host owns everything **between** sessions: fixed graphs, sequencing, timers, schedules, compensation.
- Deterministic, non-LLM steps are in scope only as tools.
- `run()` and `resume()` are idempotent per session, and escalation returns control to the caller, so a session can run as one step inside a host workflow engine (e.g. Temporal, GCP Workflows, Step Functions).
- Declarative sequential/parallel persona patterns may be considered after 1.0, only as nested sessions — never as a general graph language.

## Consequences
- The contract stays small enough for three implementations.
- Teams wanting a single declarative pipeline use agentry plus their workflow engine.
- Integration notes for common engines accompany the HITL and orchestration specs.

## Alternatives considered
- **Built-in workflow graphs** — convenient, but competes with mature engines and greatly enlarges the contract.
- **No coordination at all** — forces glue code even for simple delegation.
