# Design notes — Content: messages, multimodal parts, structured output

**Status:** Settled 2026-10-31 · **Date:** 2026-10-31
**Feeds:** Area 1 (Core model — event payloads) and Area 9 (Providers)
**Related:** `notes/core.md` (events, K3 payload size), `notes/security.md` (provenance, taint), ADR-0005 (streaming), ADR-0008 (provenance and taint), ADR-0015 (sensitivity labels)

> Non-normative working notes. Nothing here is binding until it appears in the Area 1 and Area 9 specs and conformance fixtures.

---

## 1. Position

Events carry content: what the principal said, what the model answered, what tools returned. This note fixes **one content model** for all of them, so text, images, files, structured data, and tool traffic share the same provenance, sensitivity, and size rules.

## 2. Messages and parts

- A **message** has a role and an ordered list of **content parts**.
- Roles: `system` (persona and policy instructions), `principal`, `assistant` (the model), `tool`.
- Every part carries a **provenance**, a set of **sensitivity labels**, and, for binary data, a media type.

| Part type | Holds | Notes |
|---|---|---|
| `text` | Plain text | |
| `image` | An image, by blob reference | Media types such as `image/png`, `image/jpeg` |
| `file` | A document, by blob reference | Media types such as `application/pdf`, `text/csv` |
| `structured` | A JSON value conforming to a declared schema | Used for structured output |
| `tool_call` | A tool name, arguments, and call ID | Emitted by the model |
| `tool_result` | A tool result (ok or error) with its call ID | Returned to the model |
| `reasoning` | Provider reasoning content, possibly opaque | See §6 |

The part list is closed in the core; new part types require a spec change. Adapter-specific data goes in `extensions`.

## 3. Binary content

- Images and files live in the **BlobStore** port and are referenced by a **blob reference**: ID, content hash, media type, size. Blob references are tenant-scoped like every storage record.
- Events never inline binary data. This applies the K3 rule (large payloads by reference) to all binary content.
- Provider adapters fetch blobs and encode them in whatever form the provider requires.
- Per-part and per-session size limits are set in the harness profile (`min` merge rule).

## 4. Provenance and trust of content

- A principal's **typed request** has `principal` provenance: trusted as a request, never as policy (ADR-0008).
- **Attachments** (images, files) can hide instructions — text in an image, a white-on-white paragraph in a PDF. See question T1.
- Text extracted from an image or file (OCR, PDF parsing) inherits the provenance of the original part.
- Parts produced by tools carry `tool:<name>` provenance and the tool's labels (ADR-0015).

## 5. Structured output

- A persona or harness profile may declare an **output schema** (JSON Schema) for the final response.
- When one is declared, the response must contain a `structured` part that validates against it. A `text` part may accompany it.
- The harness uses the provider's native structured-output support when available (see the providers note); otherwise it validates the model's output itself.
- On validation failure the harness asks the model to correct its output, up to a limit set in the profile. Each retry is a step and counts toward the step limit and budget.
- If the limit is reached, the run ends `failed` with error code `agentry.output.schema_mismatch` (category `fatal`).
- Order of operations: model output → schema validation → `beforeResponse` hooks (which see the validated value) → release.

## 6. Reasoning content

Some providers return reasoning ("thinking") content, and some require it to be sent back unchanged in later steps for tool use to work.

- Reasoning is a `reasoning` part. It may be opaque (encrypted or signed by the provider).
- It is stored in the checkpoint, because continuation may depend on it.
- It is never shown to the principal by default and never passed to a different provider.
- Whether it appears in traces is question T4.

## 7. Hooks and content

- Hooks receive messages as parts. Binary parts are given as blob references; a hook that needs the bytes reads them through the BlobStore port.
- A `rewrite` may change text and structured parts, and may remove or replace a binary part. It may not edit binary content in place.
- An `annotate` may add labels to individual parts (e.g. a DLP hook labels a scanned document `phi`).

## 8. Decisions (settled 2026-10-31)

- **T1 — Attachment trust:** Images and files are untrusted regardless of who supplied them. A principal's typed text is trusted as a request. A policy bundle may mark specific attachment sources trusted.
- **T2 — URL content:** No external URL parts in 1.0. Hosts ingest content into the BlobStore first.
- **T3 — Structured output and streaming:** Declaring an output schema requires `buffered` delivery. A `streamed` profile with an output schema is a configuration error.
- **T4 — Reasoning in traces:** Excluded by default; a profile may include it, labelled and redacted like any content. Always kept in the checkpoint.
- **T5 — Audio and video:** Deferred to after 1.0; may be added in a minor release as new part types.
- **T6 — Unlabelled attachments:** The harness profile declares default labels for attachments, applied until a hook labels them.

## 9. Candidate domain concepts (for `domain.md` amendment)

Message · Role · Content part · Part type · Blob reference · Attachment · Output schema · Structured part · Reasoning part · Default attachment labels

## 10. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] `Message` and each content part type
- [ ] Blob reference
- [ ] Output schema declaration in persona and profile

Fixtures:
- [ ] Image part stored as blob reference; event contains no inline bytes
- [ ] Blob reference from another tenant → not found
- [ ] Attachment with injected instruction → turn tainted; mutating call escalates
- [ ] Text extracted from a file inherits the file's provenance
- [ ] Output schema satisfied on first attempt → response released
- [ ] Invalid output corrected within the retry limit → released; retries counted as steps
- [ ] Retry limit reached → run `failed`, `agentry.output.schema_mismatch`
- [ ] `beforeResponse` hook receives the validated structured value
- [ ] `streamed` profile with an output schema → configuration rejected
- [ ] Reasoning part kept in checkpoint, excluded from trace by default
- [ ] Reasoning part never sent to a different provider
- [ ] Hook `rewrite` replaces a binary part; in-place binary edit rejected
- [ ] Unscanned attachment receives the profile's default labels
- [ ] Part exceeding the size limit → `invalid_input`
