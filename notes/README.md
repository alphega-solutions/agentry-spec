# Design notes

Non-normative working notes that capture design direction before it enters the binding spec. Only `domain.md`, the area specs, schemas, and conformance fixtures are normative.

## How a note progresses

1. **Draft** — recommendations plus open questions.
2. **Decide** — open questions resolved (or explicitly deferred to Phase 3).
3. **Record** — decisions written into the note with dates; research cited.
4. **Settled** — the note is frozen; later changes are dated amendments. Candidate concepts feed `domain.md`.

Each note is one pull request; merging it settles it.

## Backlog

| Note | Covers | Feeds | Status |
|---|---|---|---|
| [tools.md](tools.md) | Tool definition, sources, scoping, execution, sensitivity labels | Phase 1; Area 4 | Settled 2026-10-31 |
| [hooks.md](hooks.md) | Hook points and results, guardrails, layering, CEL rules | Phase 1; Area 5 | Settled 2026-10-31 |
| [security.md](security.md) | Untrusted content and prompt injection, identity, tenancy | Phase 1; cross-cutting | Settled 2026-10-31 |
| [config.md](config.md) | Configuration layering, references, validation, secrets | Phase 1; Areas 2–3 | Settled 2026-10-31 |
| [core.md](core.md) | Session lifecycle, events, stop reasons, error model | Phase 1; Area 1 | Settled 2026-10-31 |
| [hitl.md](hitl.md) | Escalation record, reviewers, decisions, expiry | Area 6 | Settled 2026-10-31 |
| [context.md](context.md) | Context assembly, retrieval, compaction, cross-session memory | Area 7 | Settled 2026-10-31 |
| [providers.md](providers.md) | Adapter contract, model choice, capabilities, sensitivity routing, usage and cost | Area 9 | Settled 2026-10-31 |
| [content.md](content.md) | Messages, multimodal parts, structured output, reasoning | Areas 1, 9 | Settled 2026-10-31 |

Tier 3 topics (storage migration, observability, eval, orchestration) go directly into their Phase 3 specs.

## Gate to Phase 1

`domain.md` begins when tools, hooks, security, config, and core are settled. **Gate met 2026-10-31.**
