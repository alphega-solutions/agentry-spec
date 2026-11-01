# Design notes — Security: untrusted content, identity, tenancy

**Status:** Settled 2026-10-31 · **Date:** 2026-10-31
**Feeds:** Phase 1 (`domain.md` concepts) and every Phase 3 area (cross-cutting)
**Related:** `notes/tools.md` (sensitivity labels), `notes/hooks.md` (guardrails, CEL rules)

> Non-normative working notes. Nothing here is binding until it appears in `domain.md`, the area specs, and conformance fixtures.

---

## 1. Position

Guardrails stop agents from **leaking**. This note addresses agents being **hijacked** (prompt injection) and agents acting for the **wrong person or tenant**.

agentry's stance: the model cannot be trusted to tell instructions from data. Prompt formatting helps, but the spec never relies on it. Safety comes from tracking where content came from and constraining what a turn may do as a result.

## 2. Threats in scope

| Threat | Example |
|---|---|
| Direct prompt injection | User input tries to override persona instructions |
| Indirect prompt injection | A retrieved document or tool result contains instructions ("ignore previous instructions and email…") |
| Exfiltration | Injected content steers the agent to send sensitive data out through a tool |
| Confused deputy | Agent uses its own broad credentials for a user who lacks the rights |
| Privilege escalation via delegation | A sub-agent gets wider tool scope than its caller |
| Cross-tenant leakage | Checkpoint, memory, retrieval, or cache returns another tenant's data |
| Guardrail manipulation | Injected content targets a model-judged hook |

Out of scope: model weight attacks, provider-side compromise, host application authentication.

## 3. Provenance labels

Every piece of content in a session carries a **provenance** — where it came from — alongside its sensitivity labels.

| Provenance | Source | Default trust |
|---|---|---|
| `system` | Persona and policy instructions | Trusted |
| `principal` | The user or calling system's request | Trusted as a *request*, never as *policy* |
| `tool:<name>` | Tool results | Untrusted |
| `retrieval:<source>` | RAG content | Untrusted |
| `agent:<persona>` | Sub-agent output | Inherits the most untrusted provenance the sub-agent saw |
| `model` | The model's own output | Inherits the provenances in its context |

- Trust is assigned by configuration, not by the content. A tool can be declared `trustedOutput: true` only through a policy bundle (e.g. an internal scheduling API), never by a persona or the tool itself.
- Provenance survives transformation: compaction summaries carry the union of the provenances they summarize.
- Provenance is recorded in traces so audits can show what influenced an action.

## 4. Taint rule

A turn is **tainted** when untrusted content is in its context window.

| Situation | Default | Configurable per tool (`onTainted`) |
|---|---|---|
| Tainted turn requests a **mutating** tool | `escalate` (human approval) | `escalate`, `block`, `allow` |
| Tainted turn requests an **egress** tool while sensitive-labelled content is in context | `block` | `block`, `escalate` |
| Tainted turn requests a **read** tool | `allow` | — |

- **Egress** is a new tool property: the tool sends data outside the trust boundary (email, SMS, external HTTP, file share). Proposed addition to the tool definition: `egress: true`.
- The exfiltration rule combines **sensitivity × egress × taint**. It is the main defence against "read the record, then send it somewhere".
- Lower configuration layers cannot loosen these defaults (same layering rule as hooks).
- Rule evaluation is deterministic and runs in the harness, before `beforeToolCall` hooks.

### Model-judged hooks

A model-judged guardrail reads untrusted content and can itself be injected. Mitigations:
- Its output is constrained to the hook result schema; free text is ignored.
- It runs with no tools.
- Profiles may require a deterministic (rule or remote) guardrail alongside any model-judged one for `block`-capable points.

## 5. Identity: the principal

- The **principal** is who the session acts on behalf of: subject ID, tenant ID, roles, attributes, and how strongly they were authenticated.
- The host application authenticates and supplies the principal. agentry never authenticates anyone.
- The principal is **immutable for the life of a session**, including across `resume`.
- Unattended runs (schedules, pipelines) use an explicit **service principal**. There is no anonymous mode.
- Principal attributes are available to CEL rules (attribute-based policies, e.g. "only clinicians may call `read_chart`").

### Delegation

- A sub-agent inherits the caller's principal.
- Its tool scope is the **intersection** of the caller's runtime scope and the sub-agent persona's allowlist. Delegation can only narrow.

### Credentials

- Tool bindings obtain credentials from a secrets provider, **keyed by the principal**, so calls run with the user's rights (on-behalf-of token exchange) wherever the target system supports it.
- Where only a shared service credential exists, the binding must enforce the principal's permissions itself, and the tool definition must declare `credentialMode: service`. This is the confused-deputy guard: it is visible and auditable.

### Reviewers

- A human reviewer in an escalation is a separate principal, recorded in the audit log with the decision. A reviewer's identity never replaces the session principal.

## 6. Tenancy

- Every session has a mandatory tenant ID, taken from the principal.
- **Every storage port is tenant-scoped** by contract: checkpoints, idempotency keys, traces, audit, blobs, vectors, memory. A lookup with the wrong tenant behaves as "not found", never "forbidden" (no existence leaks).
- Retrieval is filtered by tenant and by the principal's access rights **inside the port**, not after results return.
- Caches (prompt, embedding, tool result) are keyed by tenant.
- Cross-tenant operations do not exist in 1.0.

## 7. Decisions (settled 2026-10-31)

- **S1 — Internal tool trust:** No default trust. A tool's output is trusted only when a policy bundle lists it with `trustedOutput: true`.
- **S2 — Taint lifetime:** Sticky for the rest of the session in 1.0. Taint does not clear when compaction drops the untrusted content.
- **S3 — Egress classification:** Separate `egress` flag on the tool definition, independent of `effect`. A tool may be both mutating and egress.
- **S4 — Content delimiting:** Provider adapters MUST mark untrusted content in prompts (e.g. tagged blocks). The spec states this is defence in depth, not a security boundary.
- **S5 — Principal assurance:** Tools may declare a minimum authentication strength (optional property). It is evaluated with the taint rule, before hooks.

## 8. Candidate domain concepts (for `domain.md`)

Provenance · Trust level · Taint · Egress · Principal · Service principal · Tenant · Delegation scope · Credential mode · Reviewer · Threat (glossary only)

## 9. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] Provenance on content parts and events
- [ ] `Principal`
- [ ] Tool definition additions: `egress`, `onTainted`, `credentialMode`, minimum assurance; `trustedOutput` settable only in policy bundles

Fixtures:
- [ ] Retrieved document with injected instruction → mutating tool call escalates
- [ ] Sensitive content in context + tainted turn + egress tool → blocked
- [ ] Untainted turn → mutating tool follows normal approval policy
- [ ] Compaction summary inherits provenance and taint
- [ ] Sub-agent output carries the sub-agent's untrusted provenance back to the caller
- [ ] Sub-agent scope is the intersection of caller scope and its allowlist
- [ ] Persona tries to mark a tool `trustedOutput` → configuration rejected
- [ ] Principal unchanged across `resume`
- [ ] Session without principal → rejected
- [ ] Checkpoint load with wrong tenant → not found
- [ ] Retrieval returns only the principal's permitted documents
- [ ] Model-judged hook output outside the result schema → treated as error (fail closed)
- [ ] Principal below a tool's minimum assurance → call refused
- [ ] Untrusted content is delimited in the provider request
