# ADR-0016: Memory as a port with references that keep provenance and labels

**Status:** Accepted 2026-11-14 · **Date:** 2026-11-14 · **Source:** `notes/memory.md` §3–6, §10 (decisions M1–M4, M7, M8); `notes/context.md` X1

## Context
Under X1 the 1.0 core has no memory concept: hosts expose memory as ordinary tools, so the tool pipeline and the taint rule govern it, and tool results may now report their labels (TOOL-071 as amended 2026-11-14). That makes host memory safe enough for 1.0. It leaves to each host:
- where memory lives and how it is scoped;
- whether recalled content keeps its provenance;
- how erasure reaches everything derived from a principal's data;
- how episodes relate to the sessions they summarise.

A 1.x memory extension needs one contract for these, so that every implementation governs memory the same way.

## Decision
- **Port.** A `MemoryStore` port in Area 10, separate from the vector store. Keyword search is required; vector search is optional and declared by the adapter. Entries are versioned, never edited in place. Each stores its labels, provenances and `sources` (the sessions and events it was derived from), and returns them on read.
- **Scope.** Every operation is tenant-scoped (ADR-0014). Entries are principal-scoped by default, and tenant-wide entries are opt-in per store. No session reads another principal's memory, whatever the reviewer's or administrator's role. Administrative access is a separate host operation, and every such read is audited.
- **Memory references.** A recalled item is a memory reference (store, kind, id, version, labels, provenances, sources), recorded in an event, so audit and replay see what entered context. Replay reuses recorded recalls rather than querying the store.
- **Trust.** Recalled content has provenance `memory:<store>` and is untrusted unless a policy bundle lists the store in `trustedMemoryStores` (merge `intersect`, settable only in bundles). Untrusted recall taints the session (ADR-0008). Its labels apply to the recalled parts and join the session label set (HOOK-127). A personal preference recalled from memory carries provenance `principal`, never `system`.
- **Reading.** The first 1.x release recalls by tool only (`recall`, `recall_episode`), governed like any tool. Automatic recall, with a relevance gate that fails closed and `context.memory` limits, follows in a later 1.x release.
- **Episodes.** One episode per closed session: a summary built like a compaction summary, with the least-trusted provenance and the union of the labels of what it summarises (CTX-081), and `sources` linking it to the session's events. An episode lives no longer than its source session's events (PORT-110).
- **Consolidation.** Turning episodes or history into facts runs as an ordinary session: a service principal, its own persona, leases, budget, events and audit. Its input is untrusted, so the session is tainted and its `remember` calls escalate by default. Writes to a tenant-wide store always escalate for review under that store's reviewer rules. Write-side checks are specified, not left to prompts:
  - no operating state or assistant claims stored as facts;
  - nothing re-stored that the same session recalled;
  - deduplication against existing entries.
- **Erasure.** `erase(principal)` removes the principal's entries and everything derived from them, traced through `sources`. Events and audit records keep their own retention. Data under a legal hold is not erased while held; the deferral is audited, and erasure completes when the hold is released.
- **Persona reach.** A persona declares `memoryStores` (merge `intersect`). The default is none, so memory is opt-in per role. A child session uses its own persona's stores, never its parent's.

## Consequences
- Memory gets the same governance as every other content: taint, labels, routing, redaction, egress, audit and replay. There is no separate trust path.
- Memory cannot keep data past its source's retention or past an erasure, except under a legal hold, which is audited.
- Consolidation is visible and reviewable, because it is a session like any other.
- Implementations need a new port adapter and its port cases: tenant isolation, principal scoping, label round-trip, version immutability, erasure.
- Agents that rely heavily on memory are usually tainted, unless a bundle trusts a store. That is deliberate: trusting a store is an explicit organisational decision.

## Alternatives considered
- **Memory as host tools only (the 1.0 position)**: kept for 1.0, but it leaves scoping, erasure and episode lineage to each host, so implementations would diverge.
- **Reuse the vector store port**: its contract has no versioning, principal ownership, labels on every entry or erasure. Extending it would weaken it as read-only reference data.
- **Trusted memory by default**: makes every injected fact a permanent instruction channel.
- **Automatic recall from the start**: harder to govern and evaluate. Tool-only recall shows first what is worth recalling.
