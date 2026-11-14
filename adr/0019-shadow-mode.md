# ADR-0019: Shadow mode for rolling out hooks and approval rules

**Status:** Accepted 2026-11-14 · **Target:** 1.x (a rollout feature, not a 1.0 safety requirement) · **Date:** 2026-11-14 · **Source:** post-Phase 4 comparative review (managed agent platforms offer a log-only mode for new policies); Area 5 (hooks, approval rules), Area 11 (evaluation)

## Context
Adding governance is all-or-nothing today. A new guardrail hook or approval rule either enforces from its first session, or it is not deployed. Offline replay (EVAL-063, `reEvaluate`) shows how a change would have affected *recorded* sessions, but not the live distribution of inputs. A guardrail with a high false-positive rate therefore blocks real users before anyone has measured it.

Two existing mechanisms do not fill the gap:
- **`purpose: telemetry`** cannot declare `block` or `escalate` (HOOK-002), so it cannot measure how often a guardrail *would* block.
- **A staging environment** sees staging traffic, not production's.

## Decision
- **Where the mode lives.** A hook or approval rule is enforced or shadowed by the **layer that requires it**, not by the artifact itself, so the same hook can be enforced in one bundle and shadowed in another. A `requiredHooks` entry may be `{ref: id@version, mode: shadow}` as well as the plain reference. An `approvalRules` entry may be `{rule: "<CEL>", mode: shadow}` as well as the plain expression. The default `mode` is `enforce`.
- **Shadow evaluation.** A shadowed hook runs at its position in the chain, on the same view an enforced hook there would see. Its result is **recorded, never applied**:
  - the chain continues as if it returned `continue`;
  - its `rewrite` is not applied, and its `annotate` adds no labels;
  - its `block` or `escalate` stops nothing.

  A shadowed approval rule is evaluated at stage 7, and its outcome is recorded, never applied.
- **Recording.** A shadow decision is a `hook.decision` or `policy.decision` event with `shadow: true`, audited like any decision (HOOK-060), so "would have blocked" can be counted from events. Shadow `continue` results are not recorded, as for enforced hooks.
- **Shadow can never weaken governance.**
  - Merge: `mode` is `stricter`, order `enforce` → `shadow`. A lower layer may enforce a hook a higher layer shadows, but **never shadow one a higher layer enforces**.
  - The same hook required by two layers with different modes is enforced.
  - Built-in controls cannot be shadowed: the taint rule, allowlists and runtime scope, approval `always`, approval by sensitivity label (TOOL-035), the approval default (HOOK-133), sensitivity routing, and output-schema validation.
- **Failures.** A shadowed hook's failure is recorded (an `error` event, and a shadow `hook.decision` with the failure's code) and never blocks, whatever its `failureMode`.
- **Data rules still apply.** A shadowed hook receives content exactly as an enforced one would. Its endpoint or judge model is subject to the same sensitivity policies (HOOK-054, HOOK-092). Shadowing changes what happens *after* the decision, never what the hook may see.
- **Streaming.** Shadowed output hooks cannot recall anything, so they do not make a `streamed` profile invalid (HOOK-040, CFG-042), as telemetry hooks do not.
- **Promotion.** Moving from `shadow` to `enforce` is a configuration change: a new artifact version, loaded and pinned like any other (ADR-0007, CFG-052).
- **Evaluation.** Eval reports count shadow decisions per hook and rule. A replay under `reEvaluate` may evaluate shadowed entries as enforced, to estimate impact on recorded sessions before shadowing live.

## Consequences
- Guardrails and approval rules can be measured on real traffic, through recorded "would-block" and "would-escalate" decisions, before they affect anyone.
- Shadowed hooks cost what enforced hooks cost (latency, model calls), and add audited events.
- A shadow decision is never a control. Since shadow can only be set for additions, and never on built-in controls or on hooks a higher layer enforces, rolling something out in shadow cannot remove existing protection.
- Spec work: Areas 2 (reference and rule shapes, merge order), 5 (shadow semantics; HOOK-040 and HOOK-060 extensions), 11 (report counts); `shadow` on the decision event payloads; fixtures:
  - a shadowed block does not block and is recorded;
  - a lower layer cannot shadow an enforced hook;
  - built-in controls reject `mode`;
  - a shadowed output hook is allowed on `streamed`;
  - a shadow hook failure never blocks.

## Alternatives considered
- **Offline replay only**: already available, but limited to recorded sessions and the inputs they happened to contain.
- **A telemetry twin of each guardrail**: telemetry hooks cannot declare `block`, and keeping two hooks in sync invites drift.
- **Mode on the Hook artifact**: one hook could not be enforced in one bundle and shadowed in another. Lower layers would also need to change the artifact to promote it.
- **Allowing any layer to shadow any hook**: a persona could silently disable a bundle's mandatory guardrail.
