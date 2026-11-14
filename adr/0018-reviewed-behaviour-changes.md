# ADR-0018: Learned behaviour changes only through review

**Status:** Proposed 2026-11-14 · **Date:** 2026-11-14 · **Source:** `notes/memory.md` §2, §6.4, §8

## Context
Agents can learn procedures or standing rules from their sessions. Suppose an agent could write a skill or a persona instruction that takes effect directly: the content would be live (written at run time) and trusted (loaded as `system`). One injected turn would then become a permanent instruction for every later session. The taint rule cannot help, because once loaded, the content no longer looks untrusted.

## Decision
- **No runtime path to behaviour.** No tool, hook or memory write changes a persona, skill, policy bundle or profile. There is deliberately no configuration field that memory can write to.
- **Proposals.** An agent may call `propose_skill`, and similarly propose changes to persona instructions. A proposal raises a review (Area 6) carrying the proposed artifact, or the change as a diff against the current version. It is reviewed under the reviewer rules for its source. Self-approval is not allowed.
- **Adoption.** An approved proposal is not applied by the harness. It is handed to the host as a configuration change, and becomes a new artifact version through the normal configuration load and snapshot (ADR-0007). Running sessions keep their pinned snapshot (CFG-052).
- **Provenance.** A proposal records the session and events it came from, so a reviewer can see what prompted it, including whether the session was tainted.

## Consequences
- Learned behaviour is as reviewable, versioned and reproducible as authored behaviour.
- Agents can still improve over time, at the speed of review.
- Hosts need a path from approved proposals to their configuration source (CFG-110 leaves the config source to the host).
- Fixtures cover: a proposal raises a review; nothing changes until a new configuration load; a tainted session's proposal shows its taint to the reviewer.

## Alternatives considered
- **Agent-written skills take effect immediately, with prompt-level "ask first" instructions**: not enforceable, and the injection path stays open.
- **Agent-written skills take effect immediately as untrusted content**: skills are instructions, so untrusted instructions would be a contradiction, and they would still steer the model.
- **No learning at all**: safe, but gives up a real capability that review makes safe.
