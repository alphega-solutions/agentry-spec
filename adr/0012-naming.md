# ADR-0012: Package naming under the alphega namespace

**Status:** Accepted 2026-10-31 · **Date:** 2026-10-31 · **Source:** `intent.md` §1 Purpose, Q9, and §10 follow-up tasks

## Context
The unscoped name `agentry` is taken on npm and PyPI. Names must be consistent across three ecosystems and safe from import collisions.

## Decision
- "agentry" is the product name; every published artifact is qualified by `alphega`:
  - npm: `@alphega/agentry[-<part>]`
  - PyPI: `alphega-agentry[-<part>]`, imported via the `alphega.agentry` namespace package (never a bare `agentry` import)
  - Maven: `io.alphega:agentry-<part>`, package `io.alphega.agentry`
- Spec artifacts: `@alphega/agentry-spec`, `alphega-agentry-spec`, `io.alphega:agentry-spec`.
- Adapters: `-provider-<name>`, `-store-<name>`, or the framework name (e.g. `-langchain`).

## Consequences
- The publisher is obvious to reviewers; no collisions with existing `agentry` projects.
- Namespaces must be claimed on npm, PyPI, and Maven Central (via alphega.io DNS verification).

## Alternatives considered
- **A new unscoped product name** — loses the established name.
