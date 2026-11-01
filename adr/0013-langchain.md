# ADR-0013: LangChain is an optional integration, never a core dependency

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` Q1

## Context
LangChain overlaps with agentry: it has its own agent loop, tool abstraction, memory, and retrievers. Wiring it into the core would create competing loops and state.

## Decision
- Permitted, as optional adapters:
  - A provider adapter wrapping LangChain chat models, with LangChain's tool loop disabled.
  - Importing LangChain tools as scoped, governed agentry tools.
  - LangChain retrievers and vector stores behind the RAG port.
- Excluded: LangGraph or AgentExecutor as the loop, LangChain memory as session state, LangChain types in the contract.
- Post-1.0: exposing a persona as a LangGraph node.
- Spring AI is the primary Java integration; LangChain4j adapters are deferred.

## Consequences
- Clients can reuse LangChain assets without giving up governance.
- The provider contract must accommodate framework-wrapping adapters, which tests its vendor neutrality.

## Alternatives considered
- **LangChain as a core provider** — two loops and two memories competing for control.
- **No LangChain support** — needlessly excludes a large ecosystem, especially in Python.
