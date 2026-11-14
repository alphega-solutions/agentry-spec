# ADR-0017: Skills are configuration artifacts, loaded on demand by the model

**Status:** Proposed 2026-11-14 · **Date:** 2026-11-14 · **Source:** `notes/memory.md` §2, §6.4, §7, §8 (decisions M5, M6)

## Context
Procedural knowledge ("how to do X") could live in persona instructions, in memory, or in a unit of its own:
- **In persona instructions**, every procedure costs tokens on every call, and procedures cannot be shared across personas.
- **In memory**, a procedure is live and unreviewed content that takes effect as behaviour.

The boundary rule in `notes/memory.md` §2 settles where it belongs: behaviour is configuration, and knowledge is memory.

## Decision
- **Artifact.** `Skill` is a new configuration kind (CFG-002): `id`, `version`, `description` (when it applies), `instructions` (the procedure), `tools` (references it uses), and `requiredHooks` (hooks it adds). Like every artifact it is versioned, validated at load and pinned in the snapshot (CFG-050, CFG-052).
- **Persona.** A persona lists `skills` (`id@version`, merge `union`). Bundle `requiredSkills` is deferred until an organisation needs to mandate a procedure.
- **Reach.** Every tool a skill references must be in the persona's `tools`, checked at load (as CFG-082). A skill narrows what the agent can reach and never widens it (as ORCH-013). A skill may add hooks and never remove them.
- **Precedence.** System content is ordered policy instructions, then persona instructions, then loaded skills. Skills operate within the role and cannot override it. A skill cannot change the persona's `outputSchema`.
- **Loading.** The persona's skill index (ids and descriptions) is in system content. The model chooses a skill and loads its instructions with the built-in `load_skill` tool. The choice is a recorded tool call, so it is auditable and replays. There is no automatic matching of skills to the input: keyword matching is easy to hijack with trigger words. Loaded instructions have provenance `system`.
- **Persona or skill.** Who the agent is for the whole session (role, reach, output contract) is a persona. What it does when a task calls for it is a skill. The same content can be either. The deployment chooses.

## Consequences
- Procedures are shared across personas and cost tokens only when used.
- Skill behaviour is reproducible: a session keeps its skill versions, and replay with the recorded snapshot reproduces them.
- A skill cannot be a privilege escalation: it adds no tools and removes no hooks.
- Implementations need the new kind in their loader, the `load_skill` tool, and its fixtures (load-time reach check, precedence, recorded loading, replay).

## Alternatives considered
- **Procedures in persona instructions only**: no sharing, and a constant token cost.
- **Skills as memory**: live and unreviewed content taking effect as trusted behaviour (see ADR-0018).
- **Automatic matching on the input**: cheaper per call, but hijackable, and harder to audit than an explicit choice.
