# Design notes — Tools

**Status:** Settled 2026-10-31 (non-normative working notes) · **Date:** 2026-10-31
**Feeds:** Phase 1 (`domain.md` concepts) and Phase 3 (Area 4 — Tools spec)

> These notes capture agreed direction. Nothing here is binding until it appears in `domain.md`, the Area 4 spec, and conformance fixtures.

---

## 1. Core idea

Every tool is split in two:

- **Tool definition** — language-neutral, lives in the spec. Carries everything governance acts on.
- **Binding** — language-specific, tells an implementation how to invoke it.

All tool sources are normalized into the same definition, so the harness treats every tool identically regardless of origin.

## 2. Tool definition (draft shape)

```yaml
tool: schedule_appointment
description: Book a slot for a patient
input:  { $ref: schemas/schedule-input.json }
output: { $ref: schemas/schedule-output.json }
effect: mutating          # read | mutating
idempotent: true          # requires an idempotency key
approval: policy          # never | policy | always → HITL hook
sensitivity: [phi]        # label set; drives redaction and provider routing
timeoutMs: 10000
binding: { kind: native, ref: scheduling.book }
```

### Sensitivity labels (decided 2026-10-31: extensible)

- `sensitivity` is a **set of labels**, not a single value. An empty set means no special handling.
- The spec defines **well-known labels** with standard meaning: `pii`, `phi`, `pci`, `secret`.
- Deployments may add **custom labels**, namespaced to avoid collisions: `<reverse-domain>:<label>`, e.g. `io.alphega:clinical-notes`. Un-namespaced labels are reserved for the spec.
- Labels carry no behaviour on their own. **Sensitivity policies** in configuration map labels to behaviour: redaction rules, allowed providers, trace handling, approval escalation.
- **Fail closed:** a label with no policy mapping is a configuration error at load time. An implementation must never silently ignore an unknown label.
- When several labels apply, the strictest outcome of each behaviour wins (e.g. the intersection of allowed providers).
- Labels propagate: a tool result inherits the tool's labels, so `afterToolCall` hooks and the tracer can act on them.

## 3. Tool sources

All produce tool definitions.

| Source | Binding kind | Notes |
|---|---|---|
| Native functions | `native` | Decorator/annotation per language generates the definition: Pydantic (Python), Zod or JSON Schema (TypeScript), `@AgentryTool` or an adapter over Spring AI `@Tool` (Java). For in-process tools. |
| MCP servers | `mcp` | agentry is an MCP client. **Primary cross-language reuse path:** a tool written once as an MCP server serves all three implementations. MCP annotations (read-only, destructive, idempotent hints) are treated as untrusted; agentry configuration sets `effect`, `approval`, and `sensitivity`. |
| HTTP / OpenAPI | `http` | Definitions generated declaratively from OpenAPI operations. No code. |
| Sub-agents | `agent` | Delegation (per Q4): a persona invoked as a tool; runs as a nested session with its own budget and trace. |
| Framework imports | `langchain` | Optional adapter (per Q1). |

## 4. Scoping

Three layers; the model sees only the intersection:

1. **Catalog** — every tool known to the deployment.
2. **Persona allowlist** — declared in the persona.
3. **Runtime scope** — narrowed per call by the host's authorization context (principal, tenant, role).

The **registry** decides visibility. The **harness tool executor** enforces execution policy.

## 5. Execution contract

- **ToolContext** passed to every call: session ID, principal (who the call acts for), idempotency key, deadline, cancellation signal, trace span.
- **ToolResult** is `ok` or `error`. Errors carry a category:
  - `retryable` — executor may retry per profile policy
  - `invalid_input` — returned to the model to correct
  - `unauthorized` — not retried; may trigger escalation
  - `fatal` — ends the turn with an error stop reason
- Results pass through `afterToolCall` hooks (e.g. PHI redaction) **before** the model sees them.
- Outputs above a size threshold go to the BlobStore port; the model receives a reference.
- **Credentials never enter model context.** Bindings obtain them from a secrets provider.
- `effect: mutating` + resume: the executor MUST NOT repeat a call whose idempotency key already completed.

## 6. Outward exposure (post-1.0)

Publish a persona as an MCP tool so external agents (e.g. Claude Code) can call a governed agentry agent. Low cost once inbound MCP exists.

## 7. Candidate domain concepts (for `domain.md`)

Tool definition · Binding · Tool source · Tool catalog · Persona allowlist · Runtime scope · Principal · Tool context · Tool result · Error category · Idempotency key · Effect · Approval policy · Sensitivity label · Sensitivity policy

## 8. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] `ToolDefinition`
- [ ] `ToolResult` with error categories
- [ ] `ToolContext` (data portion)

Fixtures:
- [ ] Tool timeout
- [ ] Retryable error, then success
- [ ] `invalid_input` corrected by the model
- [ ] Call outside runtime scope → `unauthorized`
- [ ] `approval: always` → escalation, then resume
- [ ] Resume after a completed mutating call → no repeat
- [ ] Oversized result → blob reference
- [ ] MCP tool whose hint contradicts agentry config → agentry config wins
- [ ] Unmapped custom sensitivity label → configuration rejected at load
- [ ] Two labels with conflicting provider allowlists → intersection applied
- [ ] Labelled tool result → labels visible to `afterToolCall` hook and tracer

Separate spec section:
- [ ] MCP import rules (mapping, trust, scoping)

## Amendment 2026-10-31 — from `notes/security.md`

The tool definition gains: `egress` (sends data outside the trust boundary), `onTainted` (`escalate` | `block` | `allow`), `credentialMode` (`principal` | `service`), and an optional minimum authentication strength. `trustedOutput` can be set only in a policy bundle. Results also carry **provenance** (`tool:<name>`), untrusted by default.

