# agentry — Intent

**Status:** Approved 2026-10-31 (Phase 0) · **Owner:** John Akinyele, Alphega Solutions · **Date:** 2026-10-31

> This document fixes *why* agentry exists and *what* the contract covers. It deliberately contains no schemas, APIs, or implementation detail. Approval of this document gates Phase 1 (domain model).

---

## 1. Purpose

agentry is a provider-agnostic framework for building governed, production-grade AI agents.

This repository, `agentry-spec`, is agentry's **single source of truth**. It defines the concepts, behaviours, data formats, and conformance tests that every agentry implementation must satisfy. Implementations live elsewhere and depend on this repository; this repository depends on nothing.

The contract is public and open to outside review. Three reference implementations are planned, and they are private for now:

- **TypeScript** — `@alphega/agentry` (npm)
- **Java / Spring AI** — `io.alphega:agentry-core` and `io.alphega:agentry-spring-boot-starter` (Maven), package `io.alphega.agentry`
- **Python** — `alphega-agentry` (PyPI), imported as `alphega.agentry`

This repository publishes the generated spec artifacts as `@alphega/agentry-spec`, `io.alphega:agentry-spec`, and `alphega-agentry-spec`. "agentry" is the product name; the `alphega` namespace qualifies every published artifact.

An implementation is "agentry" if, and only if, it passes this repository's conformance suite.

## 2. Who it serves

1. **A HIPAA-covered healthcare platform** — the first and primary consumer. Its agents run in a HIPAA-covered environment, which sets the bar for governance, audit, and data handling.
2. **Alphega Solutions client engagements** — teams that need agents on their own stack (Node, Spring, or Python) and their own infrastructure.
3. **Agent authors** — people who define personas, tools, and policies declaratively, without writing loop or plumbing code.
4. **Operators and reviewers** — people who audit, evaluate, and approve agent behaviour.

## 3. Goals

- **G1 — One contract, many implementations.** Behaviour is specified once and verified by shared conformance fixtures, not by each implementation's own tests.
- **G2 — Declarative by default.** Personas, harness profiles, tool scopes, and policies are configuration, not code.
- **G3 — Governance first.** Guardrails, human-in-the-loop escalation, audit, and redaction are core concepts, not add-ons.
- **G4 — Provider-agnostic.** Switching model providers changes configuration, not agent definitions.
- **G5 — Infrastructure-agnostic.** Storage, tracing, and vector search are ports with swappable adapters.
- **G6 — Measurable.** Every run produces a structured, replayable trace that serves audit, evaluation, and regression testing alike.
- **G7 — Evolvable.** The contract is versioned, and changes are additive unless a major version says otherwise.

## 4. Non-goals

- **Not a hosted platform.** agentry is a library and a contract; it does not run a service.
- **Not a UI framework.** Any tooling UI (trace viewer, review queue) consumes the contract; it is not part of it.
- **No provider-specific features in the core.** Provider capabilities are reached through adapters and optional extensions.
- **Not a model-training or fine-tuning tool.**
- **Not a replacement for application authorization.** agentry enforces tool scopes and policies; the host application still owns identity and access control.
- **No third-party agent loop inside the harness.** Frameworks such as LangChain/LangGraph may supply models, tools, or retrievers through adapters, but never own the loop, session state, or memory.
- **Not a workflow engine.** Deterministic control flow across sessions (fixed graphs, sequencing, timers, schedules, compensation) belongs to the host's workflow engine. agentry sessions are designed to run as steps within one.

## 5. Scope map

The contract will eventually specify each of these areas. Order reflects intended priority, not commitment.

| # | Area | Covers |
|---|------|--------|
| 1 | **Core model** | Session, turn, event stream, stop reasons, identifiers, versioning |
| 2 | **Personas** | Declarative agent definition: role, instructions, allowed tools, policies |
| 3 | **Harness profiles** | How a persona runs: limits, budgets, context strategy, checkpointing, trace settings |
| 4 | **Tools** | Tool definition, scoping, execution semantics, mutating vs. read-only, idempotency |
| 5 | **Hooks and guardrails** | Hook points, hook results, guardrail pipelines |
| 6 | **Human-in-the-loop** | Escalation, checkpoint, decision, and resume |
| 7 | **Context and RAG** | Context assembly, additive-only retrieval, compaction |
| 8 | **Orchestration** | Agent-driven delegation only: sub-agents invoked as tools, each a nested session with its own budget and trace |
| 9 | **Providers** | The adapter contract every model provider must meet, including adapters that wrap another framework (e.g. LangChain) |
| 10 | **Storage ports** | Checkpoints, idempotency, traces, audit, blobs, vectors — behaviour, not vendors |
| 11 | **Evaluation and testing** | Eval cases, graders, trace replay, scripted providers, conformance runners |

## 6. Principles

1. **Contract before implementation.** No behaviour exists until it is specified here and covered by a fixture.
2. **Declarative over code.** If an author must write code to express a common need, the contract is missing a concept.
3. **Separation of concerns.** Personas say *who*, profiles say *how*, registries say *which tools*, hooks say *whether*.
4. **Governance is not optional.** Every mutating action is auditable, and every escalation is resumable. Where speed and governance conflict (for example, streaming vs. output guardrails), the safe behaviour is the default and the trade-off must be declared.
5. **Fixtures are the arbiter.** When prose and fixtures disagree, the fixture is fixed or the prose is fixed — never the implementation alone.
6. **Small, versioned steps.** The contract grows area by area through reviewed phases.
7. **The session is the unit of durability.** agentry owns everything inside a session; the host owns everything between sessions. `run` and `resume` are idempotent per session, and escalation returns control to the caller.

## 7. Constraints

- **HIPAA.** The contract must support PHI redaction, append-only audit, regional data residency, and provider restriction per persona. Fixtures and examples contain synthetic data only.
- **Three languages from the start.** Every concept must be expressible idiomatically in TypeScript, Java, and Python. A concept that only fits one language's idioms is a design smell.
- **Language-neutral formats.** Contract artifacts are data (schemas, fixtures) and prose — never code in one language.
- **Versioning.** Every persisted or emitted artifact carries a contract version.
- **Public contract, private implementations.** Nothing in this repository may depend on, describe, or leak private implementation code, client details, or the internals of any consuming product. The conformance suite must be runnable by anyone, so a third party could build a conforming implementation from this repository alone.

## 8. Success criteria

**Contract 1.0** is reached when:

- Areas 1–6 and 9–11 are specified, with schemas and conformance fixtures.
- All three reference implementations pass the full conformance suite.
- Native Claude and OpenAI provider adapters pass the provider conformance fixtures in all three languages. A LangChain adapter is optional and, if built, must pass the same fixtures.
- A trace recorded by any implementation can be replayed by the others' eval harnesses.
- The first consuming platform runs at least one production persona on a 1.0-conformant implementation.

## 9. How this repository evolves

Each phase is one reviewed pull request that adds one kind of artifact.

| Phase | Adds | Gate |
|-------|------|------|
| 0 | `intent.md` (this document) | Scope and non-goals agreed |
| 1 | `domain.md` — glossary and concept model | Names and relationships agreed |
| 2 | ADRs for cross-cutting decisions | Decisions accepted |
| 3 | Prose spec, area by area | Each area approved independently |
| 4 | Schemas and conformance fixtures, area by area | Fixtures read as correct |
| 5 | Codegen (TypeScript, Java, Python), CI, first published release | All three implementations can consume it |

Phases 3 and 4 proceed per area, so a mature area can reach fixtures while a later one is still in spec.

**Governance of the contract:** AI agents may draft and propose any change. Changes to intent, domain, ADRs, schemas, and fixtures require human approval, enforced through CODEOWNERS.

## 10. Carried forward

Earlier `@alphega/agentry` work (architecture spec, ADRs, roadmap, Claude Code skills) is input to Phases 1–2. Each earlier decision will be explicitly kept, revised, or retired rather than silently inherited.

- [ ] Inventory earlier ADRs and mark each keep / revise / retire.
- [ ] Number new contract ADRs from ADR-0001 (schema format, from Q3).

## 11. Open questions

- ~~**Q1 — LangChain's role.**~~ **Resolved 2026-10-31:** LangChain is an integration target via optional adapters — never a core dependency or loop owner. Permitted: a provider adapter wrapping LangChain chat models (its own tool loop disabled), import of LangChain tools as scoped agentry tools, and LangChain retrievers/vector stores behind the RAG port. Excluded: LangGraph/AgentExecutor as the loop, LangChain memory as session state, LangChain types in the contract. Exposing a persona as a LangGraph node is post-1.0. LangChain4j adapters on the Java side are deferred; Spring AI is the primary Java integration.
- ~~**Q2 — Licensing.**~~ **Resolved 2026-10-31:** The contract is public, to invite outside review and scrutiny. Reference implementations are private for now.
- ~~**Q8 — Contract license and contributions.**~~ **Resolved 2026-10-31:** Apache-2.0 for the whole repository; outside contributions require DCO sign-off.
- ~~**Q3 — Schema format.**~~ **Resolved 2026-10-31:** JSON Schema 2020-12, authored directly in YAML and published as JSON; the authored schema is the normative artifact (no TypeSpec or Protobuf layer). Conventions: stable `$id` per schema (e.g. `https://alphega.io/agentry/schemas/core/harness-event/v1.json`), unions as `oneOf` discriminated by a constant `type` field, `schemaVersion` on every top-level document, closed core objects (`additionalProperties: false`) with a single `extensions` object for vendor/adapter data. Known gap: Java codegen for unions needs a small custom generator or hand-written sealed types verified against the schemas in CI. TypeSpec may be revisited only if a hosted HTTP API with OpenAPI is ever needed. *To be recorded as ADR-0001 in Phase 2.*
- ~~**Q4 — Workflow boundary.**~~ **Resolved 2026-10-31:** agentry is the agent runtime, not a workflow engine. In scope: model-driven decisions, tools, hooks, and agent-driven delegation (sub-agents as tools). Deterministic, non-LLM steps are in scope only as tools. Out of scope: fixed graphs, cross-session sequencing, timers, schedules, compensation. Sessions are designed to be embedded as steps in host engines; integration notes for Temporal activities and callback-style engines (GCP Workflows, Step Functions) will accompany the HITL and orchestration specs. Declarative sequential/parallel persona patterns may be considered post-1.0 as nested sessions, never as a general graph language.
- ~~**Q5 — Streaming.**~~ **Resolved 2026-10-31:** The step-level event stream is core and normative (persisted, traced, conformance-tested). Token deltas are an optional `model.delta` event in the core schema: never persisted, traced, or checkpointed; if emitted, they must concatenate exactly to the final `model.response`. Delivery mode is set per harness profile: `buffered` (default — output hooks run on the full response before release) or `streamed` (deltas pass through; output hooks are advisory, and a profile is invalid if any hook declares it must block output). Abandoning a stream maps to `cancel()` and leaves a consistent checkpoint. Out of scope: transport (SSE, WebSocket, gRPC), tool-argument streaming, and incremental streaming guardrails (candidate post-1.0 extension).
- ~~**Q6 — Repository name.**~~ **Resolved 2026-10-31:** `agentry-spec`.
- ~~**Q7 — Additional implementations.**~~ **Resolved 2026-10-31:** Python is a 1.0 reference implementation alongside TypeScript and Java. Python is LangChain's native ecosystem, so the optional LangChain adapter is most natural there.
- ~~**Q9 — Package naming.**~~ **Resolved 2026-10-31:** Unscoped `agentry` is taken on npm and PyPI, so every artifact is qualified by the `alphega` namespace. Pattern: `@alphega/agentry[-<part>]` (npm), `alphega-agentry[-<part>]` (PyPI, `alphega.agentry` namespace package — never a bare `agentry` import), `io.alphega:agentry-<part>` (Maven). Adapters follow `-provider-<name>`, `-store-<name>`, or the framework name (e.g. `-langchain`).
- [ ] Claim namespaces: `alphega` org on npm, `alphega-agentry*` on PyPI, `io.alphega` on Maven Central (DNS verification via alphega.io).
- [ ] Choose private registry for implementations (recommended: Google Artifact Registry for npm, Maven, and Python) and confirm the GitHub org that will host `agentry-spec`.
