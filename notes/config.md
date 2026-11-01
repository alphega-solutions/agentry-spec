# Design notes — Configuration model

**Status:** Settled 2026-10-31 · **Date:** 2026-10-31
**Feeds:** Phase 1 (`domain.md` concepts), Area 2 (Personas), Area 3 (Harness profiles), and every area with configuration
**Related:** `notes/hooks.md` (layering), `notes/tools.md` (tool definitions, sensitivity policies), `notes/security.md` (trust, taint defaults)

> Non-normative working notes. Nothing here is binding until it appears in `domain.md`, the area specs, and conformance fixtures.

---

## 1. Position

Layering rules are currently scattered across three notes. This note gives agentry **one configuration model**: the kinds of configuration, how they reference each other, how layers combine, and how a deployment turns files into one immutable, validated snapshot.

Two principles drive it:
- **Strictness only flows downward.** A lower layer can tighten, never loosen.
- **All or nothing.** Configuration either loads completely and validly, or nothing loads.

## 2. Configuration kinds

Each file holds one artifact with a `kind`, an `id`, a `version`, and a `schemaVersion`.

| Kind | Says | Authored by |
|---|---|---|
| `PolicyBundle` | Mandatory org rules: required hooks, sensitivity policies, trusted tools, allowed providers, taint defaults | Platform / compliance owner |
| `Persona` | **Who** the agent is: instructions, tool allowlist, required hooks, default profile | Agent author |
| `HarnessProfile` | **How** it runs: limits, budgets, context strategy, checkpointing, delivery mode, trace settings | Agent author or operator |
| `Tool` | A tool definition (per `notes/tools.md`) | Tool owner |
| `Hook` | A hook definition (per `notes/hooks.md`) | Policy or platform owner |
| `Deployment` | Where it runs: provider endpoints, storage port bindings, secrets provider, environment | Operator |

`Deployment` is a separate axis. It wires infrastructure but cannot change agent behaviour or policy.

## 3. Layers and merge rules

Behavioural layers, highest first: **PolicyBundle → Persona → HarnessProfile → run request**.

How each field combines is declared **in the JSON Schema itself**, through an annotation, so every implementation merges identically:

| `x-agentry-merge` | Meaning | Example fields |
|---|---|---|
| `union` | Lower layers add items | Required hooks, sensitivity labels |
| `intersect` | Lower layers narrow the set | Tool allowlists, allowed providers |
| `min` | Lower layers may only lower the value | `maxTurns`, token and cost budgets, timeouts |
| `stricter` | Lower layers may only move toward the stricter value in a declared order | `failClosed` > `failOpen`; `buffered` > `streamed`; `block` > `escalate` > `allow` |
| `locked` | Set once at the highest layer that sets it; lower layers may not change it | Tenant-level data residency |
| `override` | Lower layers replace the value freely (non-governance fields only) | Persona display name, description |

A lower layer that tries to loosen a value is a **configuration error**, not a silent clamp. Authors should see that their setting was refused.

## 4. References

- Artifacts reference each other by `id@version`, e.g. `tools: [schedule_appointment@2]`.
- Every reference must resolve at load time. An unresolved reference is a load error.
- A persona declares a `defaultProfile` and a list of `allowedProfiles`. A run request may choose only from that list.
- Version ranges are not allowed in 1.0. References are exact, so a snapshot is reproducible.

## 5. Loading lifecycle

1. **Discover** — read artifacts from configured sources.
2. **Parse and schema-validate** each artifact.
3. **Resolve** all references.
4. **Merge** layers using the schema's merge annotations.
5. **Semantic validation**, for example:
   - layering violations (loosening a value)
   - `streamed` profile with a blocking output hook
   - unmapped sensitivity labels
   - CEL rules that fail to compile or type-check
   - `trustedOutput` set outside a policy bundle
6. **Freeze** into an immutable **effective configuration snapshot** with a content hash.

Any error at any step means **nothing loads**. There is no partial configuration.

Configuration sources are a port (`ConfigSource`): local files by default, with adapters possible for object storage or a database.

## 6. Snapshots, reload, and resume

- A new snapshot applies only to **new** sessions.
- A running session is pinned to the snapshot hash it started with. `resume` uses the same snapshot, so a policy change never alters a half-finished session's rules midway.
- Snapshots referenced by live or resumable sessions must stay retrievable (via a storage port) until those sessions end or expire.
- If a pinned snapshot is unavailable, `resume` fails with an explicit error. It never silently falls back to the current configuration.
- Every trace and audit record carries the snapshot hash, so any decision can be traced to the exact rules in force.

## 7. Environments

- Environment overlays (`dev`, `staging`, `prod`) apply on the **Deployment** axis: endpoints, port bindings, secrets provider.
- An overlay may also **tighten** behavioural values (e.g. lower budgets in `dev`) under the same merge rules. It can never loosen policy.

## 8. Secrets

- Configuration holds only **secret references** (`secret://<provider>/<name>`), never values.
- References are resolved at bind time by a secrets-provider port, keyed by principal where applicable (per `notes/security.md`).
- Secret values never appear in snapshots, traces, or audit records.

## 9. Decisions (settled 2026-10-31)

- **C1 — Version scheme:** Plain integer versions per artifact (`schedule_appointment@2`). References are exact; no ranges.
- **C2 — Run-time overrides:** A run request may choose a profile from `allowedProfiles` and may only tighten values (`min`, `stricter`, `intersect` fields), e.g. a smaller budget for one call.
- **C3 — Packaging:** One artifact per file is the canonical form. A bundle is a directory or archive of such files.
- **C4 — Integrity:** Signed or hash-pinned configuration is optional in 1.0. The snapshot hash makes tampering detectable after the fact.
- **C5 — Policy bundle stacking:** An ordered stack of policy bundles is allowed (e.g. org, then department), merged with the same rules, so each lower bundle can only tighten.

## 10. Candidate domain concepts (for `domain.md`)

Configuration kind · Artifact · Artifact reference · Policy bundle · Persona · Harness profile · Deployment · Configuration layer · Merge rule · Effective configuration snapshot · Snapshot hash · Config source · Environment overlay · Secret reference

## 11. Spec and fixture checklist (for Phase 3/4)

Schemas:
- [ ] Common artifact envelope (`kind`, `id`, `version`, `schemaVersion`)
- [ ] `x-agentry-merge` annotation vocabulary and strictness orders
- [ ] `PolicyBundle`, `Persona`, `HarnessProfile`, `Deployment`
- [ ] Secret reference format

Fixtures:
- [ ] Each merge rule: `union`, `intersect`, `min`, `stricter`, `locked`, `override`
- [ ] Persona loosens a policy-bundle value → load rejected (not clamped)
- [ ] Unresolved `id@version` → load rejected
- [ ] One invalid artifact → nothing loads
- [ ] Run request picks a profile outside `allowedProfiles` → rejected
- [ ] Policy change after session start → resumed session keeps original snapshot
- [ ] Pinned snapshot missing → `resume` fails explicitly
- [ ] Environment overlay tightens a budget → applied; loosens a policy → rejected
- [ ] Literal secret value in a secret field → rejected
- [ ] Snapshot hash present on trace and audit events
- [ ] Run request tightens a budget → applied; loosens one → rejected
- [ ] Department policy bundle loosens org bundle → load rejected
