# agentry-spec

The open specification for **agentry**, a provider-agnostic framework for building governed, production-grade AI agents.

This repository is agentry's single source of truth. It defines the concepts, behaviours, data formats, and conformance tests that every agentry implementation must satisfy. An implementation is "agentry" if, and only if, it passes this repository's conformance suite.

## Status

| Phase | Artifact | Status |
|---|---|---|
| 0 | [`intent.md`](intent.md) — purpose, scope, goals, non-goals | Approved 2026-10-31 |
| 1 | [`domain.md`](domain.md) — vocabulary and concept model | Approved 2026-10-31 |
| 2 | [`adr/`](adr/) — architecture decision records | Accepted 2026-10-31 |
| 3 | [`spec/`](spec/) — prose specs, area by area | Approved 2026-10-31 (all 11 areas) |
| 4 | [`schemas/`](schemas/), [`conformance/`](conformance/) — schemas and fixtures, area by area | In progress (foundations, Areas 1–8) |
| 5 | Codegen, CI, first published release | Not started |

Design notes feeding these phases live in [`notes/`](notes/). Notes are non-normative.

## What is normative

Only `domain.md`, accepted ADRs, the area specs, schemas, and conformance fixtures are binding. Where prose and fixtures disagree, one of them is corrected — never the implementation alone.

## Contributing

Review and scrutiny are welcome. Contributions require [Developer Certificate of Origin](https://developercertificate.org/) sign-off (`git commit -s`). Changes to intent, domain, ADRs, schemas, and fixtures require maintainer approval.

## License

[Apache-2.0](LICENSE)
