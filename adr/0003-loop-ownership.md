# ADR-0003: The harness owns the agent loop

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` §4 Non-goals and Q1; `domain.md` §9 (Harness, Provider adapter)

## Context
Model SDKs and frameworks (Spring AI `ChatClient`, LangChain/LangGraph, vendor tool runners) can run their own tool-calling loops. If they do, agentry loses `beforeToolCall` hooks, checkpoints between tool calls, idempotency, the taint rule, and consistent traces.

## Decision
- The **harness** is the only component that runs the agent loop.
- **Provider adapters** translate one request and one response, and never run their own loop.
- Third-party agent loops are never run inside the harness; framework loops are disabled when wrapped (Q1).

**Added in this ADR (approved 2026-10-31):**
- Provider adapters never execute tools; they return tool-call requests to the harness and must disable any built-in tool execution of the SDK they wrap. (A direct consequence of loop ownership, stated explicitly here.)
- Adapter conformance fixtures verify this behaviour.

## Consequences
- Governance (hooks, taint rule, approval, idempotency) applies uniformly to every tool call regardless of provider.
- Each implementation writes its own loop instead of reusing an SDK's; the conformance suite keeps the three loops consistent.

## Alternatives considered
- **Delegating the loop to provider SDKs** — less code, but governance would vary by provider and key hook points would disappear.
