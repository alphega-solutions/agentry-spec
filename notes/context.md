# Design notes — Context: assembly, retrieval, compaction, memory

**Status:** Settled 2026-10-31 · **Date:** 2026-10-31
**Feeds:** Area 7 (Context and RAG); amendments to Area 1 (event catalog, run end reasons) and Areas 2–3 (the provisional `context` field)
**Related:** Area 1 (K5: history limits belong to the context manager; CORE-140–143 reasoning), Area 4 (tools), Area 5 (taint, HOOK-121 sticky across compaction), ADR-0008, ADR-0014

> Non-normative working notes. Nothing here is binding until it appears in the Area 7 spec and conformance fixtures.

---

## 1. Position

The **context manager** decides what the model sees at each step. Events are the complete, immutable record of a session; the context is a **view** assembled from them. Compacting the context never changes the event record.

Three questions shape this area: how retrieval enters context, how context is kept within the model's limit, and whether agentry has memory across sessions.

## 2. Assembly

For each model call, the context manager assembles, in this order:

1. **System content** — policy-bundle instructions, then persona instructions (provenance `system`).
2. **Compacted history** — summaries of older turns, if any (§4).
3. **Recent history** — messages from earlier turns, oldest first.
4. **Retrieved content** — if automatic retrieval is enabled (§3).
5. **Current turn** — the principal's input and attachments, then this turn's model outputs and tool results.

The provider adapter formats this for the provider, and delimits untrusted content (ADR-0008). `beforeModelCall` hooks see the assembled context.

Never dropped by compaction:
- system content;
- the current turn's principal input;
- tool calls and their results within the current step;
- reasoning parts the provider requires for continuation (CORE-140).

## 3. Retrieval

- **Retrieval tools** — the model decides when to search. A retrieval tool is an ordinary tool (Area 4) backed by the vector store port.
- **Automatic retrieval** — the context manager searches before the turn's first model call, using the principal's input as the query, and adds the results to context.

Either way:
- retrieved content has provenance `retrieval:<source>` and is untrusted, so it taints the session (HOOK-120);
- the vector store filters by tenant and by the principal's access rights inside the port (ADR-0014);
- retrieval is **additive**: it adds content, never replaces system content or history.

## 4. Keeping within the limit

Each model has a context limit (a provider capability, Area 9). The profile reserves room for the model's output. When assembled context would exceed the remainder, the context manager compacts.

| Mode | What it does |
|---|---|
| `none` | No compaction; overflow is an error |
| `truncate` | Drops the oldest droppable history first |
| `summarize` | Replaces the oldest droppable history with a model-written summary |

A summary is content like any other:
- provenance: the least-trusted provenance of what it summarizes;
- labels: the union of the labels of what it summarizes;
- taint persists (HOOK-121).

## 5. Memory across sessions

Nothing so far carries knowledge from one session to the next. See X1.

## 6. Decisions (settled 2026-10-31)

- **X1 — Cross-session memory:** No memory concept in the 1.0 core. Hosts expose memory as ordinary tools (e.g. `recall` read, `remember` mutating), so the taint rule guards memory writes.
- **X2 — Automatic retrieval:** Both retrieval tools and automatic retrieval are supported; automatic retrieval is off by default and enabled per profile.
- **X3 — Summarization safety:** The summarizer runs like a model-judged hook (no tools, allowed providers, sensitivity policies apply, no hooks on its calls). Each compaction is recorded in a new `context.compacted` event holding the summary; replay reuses it.
- **X4 — Overflow:** New run end reason `context_limit` (session → `idle`), error `limit` (`agentry.context.overflow`).
- **X5 — Summarization cost:** Summarizer tokens count toward the turn budget.
- **X6 — Strategy location:** A structured `context` block in harness profiles replaces the provisional `context` override field.

## 7. Candidate domain concepts (for `domain.md` amendment)

Context (finalised as a view) · Context manager (finalised) · Retrieval tool · Automatic retrieval · Compaction · Compaction mode · Summary · Reserved output tokens

## 8. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] Harness profile `context` block
- [ ] `context.compacted` event payload

Fixtures:
- [ ] Assembly order; `beforeModelCall` hook sees assembled context
- [ ] Never-dropped content survives compaction
- [ ] Compaction leaves events unchanged
- [ ] Truncate drops oldest droppable history first
- [ ] Summary carries least-trusted provenance and union of labels; taint persists
- [ ] Summarizer uses an allowed provider, no tools, no hooks
- [ ] `context.compacted` recorded; replay reuses the summary
- [ ] Automatic retrieval off by default; on: results added with `retrieval:<source>` provenance, session tainted
- [ ] Retrieval returns only the principal's permitted documents in its tenant
- [ ] Overflow after compaction → `context_limit`
- [ ] Summarizer tokens counted toward the turn budget
- [ ] Memory write tool in a tainted session → escalation
