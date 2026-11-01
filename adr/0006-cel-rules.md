# ADR-0006: CEL subset as the declarative rule language

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `notes/hooks.md` §6 and CEL research

## Context
Guardrails and policies should be expressible without code, and one rule must behave identically in TypeScript, Java, and Python.

## Decision
- Declarative rules are written in a defined **subset of the Common Expression Language (CEL)**: standard operators; macros `has`, `all`, `exists`, `exists_one`, `map`, `filter`; the strings extension; JSON-like values only. No protobuf message types and no custom functions in 1.0.
- Library choices for the reference implementations (as of 2026-10-31): `dev.cel:cel` (Java), `@bufbuild/cel` (TypeScript), `cel-expr-python` (Python).

**Added in this ADR (approved 2026-10-31):** Other implementations may use other CEL libraries, provided they pass the rule fixtures. Library choice is therefore recorded here but not part of the normative contract.
- Safeguards:
  - Shared rule fixtures (including integer division, null and missing fields, regex) that every implementation must pass.
  - Rules compile and type-check at configuration load; failure is a configuration error.
  - Each implementation evaluates rules behind a replaceable rule evaluator.
  - Library versions are pinned and rule fixtures re-run on upgrade.

## Consequences
- Policy authors write one rule for all implementations.
- The TypeScript and Python libraries are young (beta and v0.1.x); the subset and fixtures contain that risk.
- If the Python library stalls, rules can be evaluated through a remote hook as a fallback.

## Alternatives considered
- **A custom rule language** — full control, but a new language for reviewers and three interpreters to build.
- **Rego (OPA)** — powerful, but heavier and less natural to embed in all three languages.
- **Code-only hooks** — no portability across implementations.
