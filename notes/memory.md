# Design notes — Memory: skills, episodes, facts, and the persona boundary

**Status:** Draft · **Date:** 2026-11-14
**Feeds:** a 1.x memory extension (Areas 2, 6, 7, 10); one 1.0 fix to Area 4 (§9)
**Related:** `notes/context.md` X1 (no memory concept in the 1.0 core), Area 2 (personas, merge rules, snapshots), Area 4 (tool result labels, TOOL-071), Area 5 (taint, HOOK-121/122/126/127), Area 6 (review), Area 7 (retrieval, compaction, CTX-081), Area 8 (delegation, ORCH-010–013), Area 10 (ports, retention), Area 11 (replay, eval), ADR-0008, ADR-0014, ADR-0015

> Non-normative working notes. Nothing here is binding until it appears in an area spec, schema and conformance fixtures.

---

## 1. Position

Decision X1 (2026-10-31) keeps cross-session memory out of the 1.0 core: hosts expose memory as ordinary tools (`recall` read, `remember` mutating), so the taint rule guards memory writes. That remains the 1.0 position. This note covers:
- what a first-class memory model would look like in 1.x;
- how it relates to personas;
- the one gap in the tools-only approach that 1.0 should close anyway (§9).

Memory is content from the past re-entering context. Like all content, it needs three things:
- **provenance and trust:** where it came from;
- **labels:** what sensitivity it carries (ADR-0015);
- **a record:** so audit and replay can reproduce what the model saw.

Memory that skips any of these is a path around governance.

## 2. The boundary rule

> **Behaviour is configuration; knowledge is memory.**

| | Configuration | Memory |
|---|---|---|
| What | How the agent acts: role, procedures, tool reach, output contract | What the agent knows: facts, past events, preferences |
| Written by | Authors, through review and a configuration load | The harness and agents, at run time |
| Versioned and pinned | Yes: in the snapshot, so a session keeps its versions (CFG-052) | No: live; a write affects other sessions |
| Trust | Trusted (provenance `system`) | Untrusted by default |
| Replay | Reproduced from the recorded snapshot | Reproduced from recorded recalls |

**Live content is never trusted.** Something written at run time that takes effect as trusted behaviour without review is the combination to forbid: one injected turn would become a permanent instruction. Every route from memory to behaviour therefore goes through review and a new artifact version (§6.4).

## 3. Kinds of memory

| Kind | Holds | Scope | Home |
|---|---|---|---|
| **Working** | The session's own history | Session | Exists today: the event log and checkpoint, assembled and compacted by the context manager (Area 7) |
| **Episodic** | What happened: summaries of past sessions or tasks | Principal or tenant | Derived from the event log (§6.2) |
| **Semantic** | What is true: facts, entities, user preferences | Principal or tenant | A memory store port (§5) |
| **Procedural** | How to do something: instructions, steps, the tools to use | Persona or tenant | Configuration: a `Skill` artifact (§6.4) |

**Periodic consolidation** is not a kind of memory. It is a process that turns episodes into facts and may propose skills (§6.3).

## 4. The memory reference

Every recalled item is a **memory reference**, recorded in an event (as `context.retrieved` records retrieval) so audit and replay see exactly what entered context:

```yaml
memoryRef:
  store: facts               # a memory store declared in the deployment
  kind: episode | fact       # skills are configuration, not memory refs
  id: ...                    # stable within the store
  version: 3                 # entries are versioned, never edited in place
  labels: [pii]              # stored with the entry, returned with it
  provenances: [tool:lookup, model]  # what the entry was derived from
  sources: [{ sessionId, eventIds }] # traceability to the event log
  principalRef: { ... }      # owner, when principal-scoped
```

How recalled content behaves:
- **Provenance:** it enters context as parts with provenance `memory:<store>`.
- **Trust:** it is untrusted unless a bundle lists the store in `trustedMemoryStores`, mirroring `trustedTools` and `trustedAttachmentSources` (merge `intersect`). Untrusted recall taints the session (HOOK-120).
- **Labels:** the entry's labels apply to the recalled parts and join the session label set (HOOK-127). Provider routing, redaction and the egress condition therefore apply to recalled data.
- **Personal preferences** are the principal's own statements, not the organisation's. Recalled, they carry provenance `principal`, never `system`.

## 5. The memory store port

A new Area 10 port, alongside the vector store:
- **Operations:** `write`, `search`, `get`, `delete`, `erase(principal)`, and `deleteDerivedFrom(session)`.
- **Scoping:** every operation is tenant-scoped (ADR-0014). Entries may also be **principal-scoped**: readable only by the principal that owns them, or by those an `access` field names, as for vector records.
- **Entries:** each stores its labels, provenances and sources, and returns them on read.
- **Versioning:** a write never edits an entry in place, so recorded refs stay resolvable for replay and audit.
- **Port cases:** tenant isolation, principal scoping, labels round-trip, version immutability, erasure.

The deployment declares stores, as it declares vector store sources.

## 6. Read and write paths

### 6.1 Reading

Two modes, as for retrieval (CTX-030/031):
- **By tool:** `recall` (facts) and `recall_episode` (episodes), built-in tools over the port. The model asks; the call is governed like any tool.
- **Automatic:** the context manager recalls before a model call. A **relevance gate** decides whether to recall at all, since recalling on every turn costs latency and biases answers toward stored content. The gate:
  - is a model-judged or rule check with a recorded decision;
  - fails **closed** by default: on error, nothing is recalled, as a guardrail does (HOOK-053);
  - is bounded by `context.memory` limits (count, tokens).

Assembly position (Area 7 §2): after system content and loaded skills, before history, delimited as untrusted content (PROV-003).

### 6.2 Episodes

An episode is a summary of a closed session, built like a compaction summary (CTX-081):
- **Provenance:** the least-trusted provenance of what it summarises.
- **Labels:** the union of its sources' labels.
- **Sources:** the session and event IDs it was built from.
- **Built by:** the summarizer, under the same rules as compaction summaries (Area 7 X3).
- **Retention:** an episode lives no longer than its source session's events (PORT-110). Erasure of a session or principal cascades to episodes derived from it (`deleteDerivedFrom`). Without this, memory becomes a way to keep data past its retention period.

### 6.3 Writing facts, and consolidation

- **`remember`** is a mutating tool and stays governed as today: approval, hooks, and the taint rule. In a tainted session it escalates (HOOK-122).
- **Consolidation** distils episodes or raw history into facts. It runs as an **ordinary session**, not a background shortcut:
  - with a service principal and its own persona;
  - with the usual leases, budget, events and audit;
  - its input (episodes, history) is untrusted, so the session is tainted and its `remember` calls escalate by default. A bundle may loosen this for low-risk stores via `toolTaintDefaults`.
- **Write-side checks**, specified as rules rather than left to prompts:
  - do not store operating state or the assistant's own claims as facts;
  - do not re-store what the same session recalled (a feedback loop that inflates and entrenches memory);
  - dedupe against existing entries.
- **Triggers:** on session close, after N closed sessions, or on a schedule. Every trigger starts a session as above.

### 6.4 Skills

A **`Skill`** is a new configuration artifact kind:
- `id`, `version`, `description` (when it applies);
- `instructions` (the procedure);
- `tools` (references it uses) and `requiredHooks` (hooks it adds).

How skills behave:
- **Loading:** the persona's skill index (IDs and descriptions) goes into system content. A skill's body is loaded on demand by the built-in `load_skill` tool, or automatically when it matches the input. Unused skills cost no tokens.
- **Trust:** loaded bodies have provenance `system`. They are reviewed configuration, pinned in the snapshot and reproduced on replay.
- **Reach:** a skill's tools must be in the persona's `tools`, checked at load (as CFG-082). A skill narrows, never widens, what the agent can reach (as ORCH-013).
- **Learned skills are proposals.** An agent may call `propose_skill`. That raises a review (Area 6) carrying the proposed artifact. Approval produces a new artifact version through the normal configuration pipeline, not a runtime edit. The same applies to any proposed change to persona instructions.

## 7. Personas, skills and memory

### 7.1 Persona fields

| Persona field (merge) | Counterpart | Relationship |
|---|---|---|
| `instructions` (`locked`) | Skill bodies; personal preferences | Skills extend instructions and never override them. Order: policy instructions, persona instructions, loaded skills. Preferences are memory with provenance `principal`, never instructions. |
| `tools` (`intersect`) | Skill tools | A skill's tools ⊆ the persona's tools. |
| `requiredHooks` (`union`) | Skill hooks | Skills may add hooks, never remove them. |
| `outputSchema` (`locked`) | A skill's preferred output format | A skill cannot change it. A skill-specific format is structured content inside the persona's schema, or the task belongs to another persona. |
| `model`, `allowedProviders` (`intersect`) | Recalled labels | Recalled labels restrict providers through sensitivity policies (PROV-050). |
| `approvalRules`, `reviewerRules` (`union`) | Memory writes; skill proposals | Reviewed through the existing approval and reviewer rules. |

### 7.2 Distinctions

- **Role versus person.** A persona is one role, shared by everyone who uses it. Memory belongs to a tenant or a principal. So:
  - **Role conventions** ("summaries are three bullets") are persona instructions or a skill.
  - **Personal preferences** ("this user writes in British English") are principal-scoped memory.
- **Identity versus capability.**
  - **Who the agent is for the whole session:** a persona. It is chosen per session and fixes role, reach and output contract.
  - **What it does when a task calls for it:** a skill. It is loaded on demand, and many personas can share it.

  The same content can be either, for example a "solution architect" lens. It is a persona when the agent *is* the architect, and a skill when a general agent *applies* the lens on request. Agentry supports both; the deployment chooses.
- **Pinned versus live.** Skills (configuration) are pinned per session. Memory is live, which is acceptable only because it is informational and untrusted (§2).

### 7.3 Delegation

A child session gets its own persona's skills and memory stores, never the parent's. Anything the parent passes travels in the call arguments, with the parent's label set (ORCH-010, ORCH-011 as amended 2026-11-13). Memory cannot cross roles by delegation.

## 8. Proposed configuration

| Field | Where | Merge | Purpose |
|---|---|---|---|
| `skills` | Persona | `union` | Skills this persona may load (`id@version`) |
| `requiredSkills` | Policy bundle | `union` | Organisation-mandated procedures, the counterpart of `requiredHooks` |
| `memoryStores` | Persona | `intersect` | Stores this role may read or write; default none, so memory is opt-in per role |
| `trustedMemoryStores` | Policy bundle | `intersect` | Stores whose recalled content does not taint; settable only in bundles |
| `context.memory` | Bundle, profile | `min` / `stricter` per field | Automatic recall on or off, gate, limits; like `context.retrieval` |
| Memory stores | Deployment | — | Store declarations and bindings, like vector store sources |

There is deliberately **no persona field that memory can write to**.

## 9. The 1.0 fix: labels from tool results

Under X1, memory is a host tool, and a tool result carries only the labels in the tool's `sensitivity` declaration (TOOL-071) plus any a hook adds. A store that saved `pii` data returns it, through `recall`, with only `recall`'s declared labels. If `recall` declares none, the data comes back unlabelled, and routing, redaction and the egress condition no longer apply to it. The same applies to any tool that returns stored data: a CRM, a ticketing system, a file store.

**Recommendation for 1.0:**
- A tool result may carry labels of its own, which the harness **adds** to the declared ones (a union, never a removal).
- A hook may still add labels.
- Labels outside the sensitivity policies are rejected, as for hook annotations.

This makes host-provided memory safe enough for 1.0 without the 1.x extension.

## 10. Evaluation

- **Replay:** recalls are recorded, so replay reuses them instead of querying the store (as EVAL-061 does for retrieval). Consolidation sessions replay like any session.
- **Eval matrix:** a memory store dimension alongside models and profiles (EVAL-044), so stores can be compared with the harness held fixed. Scoring probes:
  - **pass:** correct;
  - **stale:** outdated;
  - **invented:** stated but never stored;
  - **miss:** stored but not recalled.

  Each probe runs in a fresh session, so answers cannot come from history.
- **Receipts:** the host can be told which memory refs shaped a response, from the recorded events.

## 11. Open questions

1. **Search model.** Vector, keyword, or both? Is the memory store a specialisation of the vector store port, or separate?
2. **Scope defaults.** Are facts principal-scoped by default, with tenant-wide facts opt-in? Who may read another principal's memory (reviewers, administrators), and is that access audited?
3. **Erasure.** Does `erase(principal)` also redact the principal's content in retained events and audit records, or only memory? How does it interact with legal holds (PORT-114)?
4. **Automatic recall in 1.x,** or tool-only first?
5. **`requiredSkills`.** Needed in 1.x, or wait for demand?
6. **Skill matching.** When automatic loading is on, how are skills matched (description overlap, a model judge, a rule)? Which signal is recorded?
7. **Consolidation scope.** Per principal only, or tenant-wide knowledge? Who reviews tenant-wide writes?
8. **Episode granularity.** Per session, or per task within a session?

## 12. Candidate domain concepts

Memory store · Memory reference · Episode · Fact · Consolidation session · Skill · Skill proposal · Relevance gate

## 13. Next steps

1. Settle the 1.0 fix (§9) as an Area 4 amendment with fixtures.
2. Resolve the open questions here.
3. ADRs:
   - **(a)** Memory store port and memory references (Areas 7, 10).
   - **(b)** `Skill` artifact and on-demand loading (Areas 2, 7).
   - **(c)** Learned skills and persona changes only through review (Area 6).
