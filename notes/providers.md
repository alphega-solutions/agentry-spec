# Design notes — Providers: adapters, capabilities, routing, usage

**Status:** Settled 2026-10-31 · **Date:** 2026-10-31
**Feeds:** Area 9 (Providers); replaces the provisional `model` field (CFG-090, CFG-092) and `compaction.model` (CTX-100)
**Related:** ADR-0003 (harness owns the loop), ADR-0008 (delimiting), ADR-0009 (errors), ADR-0013 (LangChain), ADR-0015 (sensitivity policies), Area 1 (CORE-142 reasoning), Area 7 (context limit)

> Non-normative working notes. Nothing here is binding until it appears in the Area 9 spec and conformance fixtures.

---

## 1. Position

A **provider adapter** translates one harness request into one provider call and the response back. It never loops and never executes tools (ADR-0003). This note covers how a model is chosen, what an adapter must report about it, how sensitive content constrains which model may see it, and how usage and cost are normalized across vendors.

## 2. The adapter contract

An adapter:
- converts the assembled context, visible tool definitions, and output schema into a provider request;
- delimits untrusted content (ADR-0008);
- returns the response as content parts (text, tool calls, structured, reasoning), never executing tool calls;
- maps provider errors into the agentry error model (ADR-0009);
- reports normalized usage (§6);
- declares the capabilities of each model it serves (§4).

The same adapter contract and fixtures apply to native adapters (Claude, OpenAI) and framework-wrapping adapters such as LangChain (ADR-0013).

## 3. Choosing a model

The provisional `model` field becomes a structured block:

```yaml
model:
  provider: anthropic        # provider declared in the deployment
  name: claude-sonnet-x      # model identifier
  params:                    # passed to the provider; governance-neutral
    temperature: 0.2
    maxOutputTokens: 4096
  fallbacks:                 # optional; see P3, P4
    - { provider: anthropic, name: claude-haiku-x }
```

Providers are declared in the deployment with endpoint, region, and data-handling attributes (e.g. retention), so sensitivity policies can allow or deny them.

## 4. Capabilities

| Capability | Meaning |
|---|---|
| `contextLimit` | Maximum input tokens (used by Area 7) |
| `maxOutputTokens` | Maximum output tokens |
| `toolUse`, `parallelToolCalls` | Tool calling support |
| `structuredOutput` | Native schema-constrained output |
| `vision`, `documents` | Accepts image and file parts |
| `reasoning` | Returns reasoning parts |
| `streaming` | Can emit deltas |

The harness uses capabilities to validate configuration and requests. For example, a persona with tools needs `toolUse`; an image attachment needs `vision`.

## 5. Sensitivity routing

Sensitivity policies list allowed providers per label (ADR-0015). At each model call, the model's provider must be allowed for every label in the assembled context. Labels can appear mid-session (a tool result labelled `phi`), so a model that was fine at turn 1 may not be at turn 3.

## 6. Usage and cost

- Adapters report usage in one shape: `inputTokens`, `outputTokens`, `cachedInputTokens`, `reasoningTokens`.
- Token budgets use these directly. Cost budgets need prices; vendors change prices, so they cannot be built into the spec.

## 7. Decisions (settled 2026-10-31)

- **P1 — Model block:** Structured `model` block in policy bundles, personas, and profiles. `provider` and `name` are `locked`; `params` are `override`; `fallbacks` are `intersect`.
- **P2 — Capability source:** Adapters declare capabilities; a deployment may restrict, never extend.
- **P3 — Sensitivity routing:** Use the first fallback allowed for every label in context, recording a `policy.decision`. If none, no model call; the run ends `blocked`. Content is never sent to a disallowed provider.
- **P4 — Failover:** Same-provider failover at any time; cross-provider failover only at the start of a turn. Every switch recorded.
- **P5 — Cost:** Deployment price table per model. With `budget.cost` set, every usable model (fallbacks, summarizers, model hooks) must be priced, or configuration is rejected.
- **P6 — Provider safety refusals:** Error category `policy`, source `provider`; the run ends `blocked` with the fallback message.
- **P7 — Capability mismatches:** Checked at load time where possible; otherwise per request, using the first capable allowed fallback, or failing with `invalid_input`.

## 8. Candidate domain concepts (for `domain.md` amendment)

Provider adapter (finalised) · Provider · Model · Model block · Capability · Fallback model · Sensitivity routing · Normalized usage · Price table

## 9. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] `model` block; provider declaration in the deployment; price table
- [ ] Capability declaration
- [ ] Normalized usage

Fixtures (all run against every adapter, native or framework-wrapping):
- [ ] Adapter returns tool calls; never executes them
- [ ] Untrusted content delimited
- [ ] Response mapped to content parts, including reasoning
- [ ] Provider errors mapped (rate limit → `unavailable` retryable; safety refusal → `policy`)
- [ ] Usage normalized
- [ ] Deployment restricts a capability → honoured; attempt to extend → rejected
- [ ] `phi` enters context; session model disallowed → allowed fallback used, `policy.decision` recorded
- [ ] No allowed model → run `blocked`, content never sent
- [ ] Outage: same-provider failover mid-turn; cross-provider failover only at turn start
- [ ] `budget.cost` with an unpriced model → rejected
- [ ] Persona with tools on a model without `toolUse` → rejected
- [ ] Image part, model without `vision` → capable fallback or `invalid_input`
- [ ] Bundle pins the model; persona cannot change it
