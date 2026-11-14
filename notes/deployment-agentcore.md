# Design notes — Deploying agentry on AWS Bedrock AgentCore

**Status:** Draft · **Date:** 2026-11-14
**Feeds:** implementation guidance (Phase 5); port case requirements for ADR-0016 adapters; ADR-0019
**Related:** ADR-0003 (the harness owns the loop), ADR-0004 (session durability), ADR-0008, ADR-0014, ADR-0016–0019, Areas 4, 5, 10, 11

> Non-normative. AgentCore facts were checked against AWS documentation on 2026-11-14 where cited. Items marked **verify** rest on third-party sources or are not documented, and must be confirmed before an adapter relies on them.

---

## 1. Position

AgentCore is a managed AWS platform: hosting (Runtime), memory, a tool gateway, identity, policy, evaluation, observability, and managed tools (Code Interpreter, Browser). It is framework-agnostic and does **not** own the agent loop. agentry is a contract for a harness that **does** own the loop.

They are complementary. An agentry implementation (Python, Node.js or Java) is the loop AgentCore Runtime hosts. AgentCore services back agentry ports and bindings.

**The governing rule:** agentry's pipeline is the control, and AgentCore's controls are defence in depth. No agentry guarantee may depend on an AgentCore feature that a tool, binding or configuration could bypass.

## 2. Mapping

| agentry | AgentCore | Notes |
|---|---|---|
| Harness process | **Runtime** (a microVM per runtime session) | See §3. |
| `MemoryStore` port (ADR-0016, 1.x); `recall`/`remember` tools (1.0) | **Memory** (short-term events; long-term strategies) | See §4. |
| `mcp` tool binding | **Gateway** (APIs, Lambda functions and services exposed as MCP tools) | Governance metadata (effect, egress, idempotency, approval, sensitivity) stays in agentry `Tool` artifacts. MCP results carry no labels in 1.0 (TOOL-071). |
| `credential mode: principal`; secrets provider port | **Identity** (workload identity; token vault keyed by user × agent × provider; inbound and outbound OAuth) | See §5. |
| Remote hook (HOOK-091) | **Bedrock Guardrails** | A guardrail remote hook at `beforeModelCall`, `afterToolCall` and `beforeResponse`; fails closed. |
| Defence in depth beside the tool pipeline | **Policy** (Cedar at the Gateway, deny by default, log-only mode) | See §6. |
| Telemetry exporter (PORT-100–102) | **Observability** (OpenTelemetry, CloudWatch) | Spans only. The event log and audit log remain the system of record. |
| Eval runs (Area 11) | **Evaluations** (online and on-demand; LLM-judge evaluators) | See §7. |
| Tools with `mcp` or `http` bindings | **Code Interpreter**, **Browser** | Ordinary tools. Declare `effect` and `egress` honestly: a browser is `egress: true`. |

## 3. Runtime

- **Lifetime mismatch.** A runtime session ends after 8 hours, or 15 minutes idle ([how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)). An agentry session may be suspended for days (`suspendedTtl`). So an agentry session spans many runtime sessions. This is safe because every step is checkpointed to the ports (ADR-0004, PORT-034), and `resume()` or a new `run()` simply starts a new runtime session.
- **Never rely on the runtime filesystem** for session state. AWS documents runtime state as ephemeral; some persistent-filesystem options exist (**verify** which, and their limits). All agentry state goes through the ports.
- **Leases.** A runtime session ending mid-run is a crash from agentry's point of view. The run lease lapses and recovery follows (HITL-090–092). Set `leaseTtl` well below the runtime idle limit.
- **Port adapters** used from Runtime must be durable AWS services (for example DynamoDB, S3, Aurora), never the microVM. They must meet the port contracts: tenant scoping, fencing tokens, versioned saves (PORT-020, PORT-031, PORT-040).

## 4. Memory

The taxonomy maps cleanly onto ADR-0016:
- **Semantic and user preference** strategies are facts.
- **Session summary and episodic** strategies are episodes.
- Namespace templates such as `/users/{actorId}/preferences/`, and record time-to-live per strategy, are useful ([built-in strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-configuring-built-in-strategies.html)).

The trust model differs, so an AgentCore-backed adapter must follow these rules:
1. **No unreviewed extraction into trusted memory.** Built-in strategies extract facts automatically and asynchronously from conversations. Either:
   - disable them and let agentry's consolidation session write records (ADR-0016), or
   - treat strategy output as untrusted, unlabelled input that must pass through consolidation before it is a fact.
2. **Reflections are knowledge, never behaviour.** Episodic reflections ("successful patterns") must never become skills or instructions except through review (ADR-0018).
3. **Labels, provenance and sources must round-trip.** Store them with each record. **Verify** that records support arbitrary metadata. If they do not, the adapter must refuse to store labelled content (fail closed), never drop the labels.
4. **Scope from the pinned principal.** Derive `{actorId}` and namespaces from the session's pinned principal and tenant, never from model or tool input.
5. **Erasure.** `erase(principal)` and `deleteDerivedFrom(session)` must reach every namespace holding the principal's records. **Verify** the deletion APIs per namespace.

Under 1.0 (X1), AgentCore Memory is reached through host `recall`/`remember` tools. Implement them as **native** tools so results can report labels (TOOL-071), not as Gateway MCP tools, which cannot.

## 5. Identity

- **Inbound.** The host authenticates the caller and supplies the principal. agentry never authenticates (ADR-0014).
- **Outbound.** For `credential mode: principal`, the tool binding obtains the user's token from the token vault, scoped to the **pinned principal's** identity. Never pass an identifier derived from the model, tool arguments or content. A third-party write-up reports that the user-scoped workload token API accepts a caller-supplied user ID without checking it (**verify**). Treat that ID as a trust boundary owned by the host.
- **Secrets.** Credentials in deployments stay `secret://` references (CFG-061). A secrets provider adapter may resolve them from the token vault or AWS Secrets Manager.

## 6. Policy and Guardrails

- **Gateway policy only sees calls through the Gateway.** Tools on other bindings bypass it. agentry's tool pipeline (allowlist ∩ scope, taint rule, approval, hooks) applies to every binding, so it stays the control. Cedar policy is an outer layer.
- **Different questions.** Cedar answers "may this principal call this action on this resource now?" agentry adds **information flow**: sticky taint, the session label set, egress (HOOK-120–127). Do not try to recreate taint in Cedar.
- **Log-only mode** is the AgentCore counterpart of ADR-0019's shadow mode. Use both when rolling out a control on both layers.
- **Guardrails in policy** (June 2026) evaluates gateway-target inputs and outputs ([announcement](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-agentcore-policy-guardrails-generally-available)). For agentry, a Guardrails remote hook is preferable, because it covers model calls and responses as well as tools, and its decisions are agentry hook decisions (audited, replayable).
- **Human approval.** AgentCore has no native approval primitive; AWS guidance uses Step Functions callbacks. agentry's escalations are the approval mechanism (Area 6). A Step Functions workflow can drive `resume()` (Area 6, Appendix A).

## 7. Evaluation

- Offline agentry eval runs (Area 11) can run on AgentCore in a dedicated eval tenant and deployment (EVAL-040).
- **Online evaluation** of production traffic is not in agentry 1.0. If AgentCore Evaluations scores production sessions, its judge reads production content. That is acceptable only where the judge model is allowed for every label on that content (EVAL-051, PROV-053). It does not replace agentry's offline suites.
- AgentCore's tool-call-level evaluators (tool selection, parameter accuracy) are a model for future agentry grader kinds.

## 8. Open items

1. **Verify** AgentCore Memory record metadata support, and per-namespace deletion (§4).
2. **Verify** the runtime persistent-filesystem options, and confirm the 8-hour and 15-minute limits for the chosen runtime type (§3).
3. **Verify** the user-scoped token API's identity checking (§5).
4. Decide whether agentry should specify online evaluation (via `convert`, EVAL-070) as a 1.x feature.
5. Port case additions for ADR-0016 adapters: record time-to-live, and fail-closed handling of unstorable labels.
