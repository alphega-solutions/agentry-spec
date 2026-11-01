# ADR-0001: JSON Schema 2020-12 is the normative schema format

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` Q3

## Context
The spec must define data formats that three implementations (TypeScript, Java, Python) generate from, that validate human-authored YAML configuration, and that public reviewers can read without learning new tools.

## Decision
- Schemas are **JSON Schema 2020-12**, authored directly in YAML and published as JSON.
- The authored schema is the normative artifact. There is no TypeSpec, Protobuf, or other source layer.
- Conventions:
  - Every schema has a stable `$id`, e.g. `https://alphega.io/agentry/schemas/core/harness-event/v1.json`.
  - Unions use `oneOf` discriminated by a constant `type` field.
  - Every top-level document carries `schemaVersion`.
  - Core objects are closed (`additionalProperties: false`); vendor and adapter data goes in a single `extensions` object.

## Consequences
- What reviewers read is exactly what validators run.
- The same schemas give editor autocomplete and validation for persona and profile YAML.
- Java codegen for `oneOf` unions is weak; Java uses a small custom generator or hand-written sealed types, verified against the schemas in CI.
- Readability for newcomers relies on the prose spec and generated schema docs.

## Alternatives considered
- **TypeSpec emitting JSON Schema** — more readable, but adds a generated artifact that can drift and a niche toolchain. Revisit only if a hosted HTTP API needing OpenAPI is introduced.
- **Protobuf** — strong codegen, but poor for human-authored YAML and less readable for reviewers.
