# agentry-spec

The open specification for **agentry**, a provider-agnostic framework for building governed, production-grade AI agents.

This repository is agentry's single source of truth. It defines the concepts, behaviours, data formats, and conformance tests that every agentry implementation must satisfy. An implementation is "agentry" if, and only if, it passes this repository's conformance suite.

## Status

| Phase | Artifact | Status |
|---|---|---|
| 0 | [`intent.md`](intent.md) — purpose, scope, goals, non-goals | Approved 2026-10-31 |
| 1 | [`domain.md`](domain.md) — vocabulary and concept model | Approved 2026-10-31 |
| 2 | [`adr/`](adr/) — architecture decision records | Accepted 2026-10-31 (ADR-0001–0015); ADR-0016–0020 accepted 2026-11-14 |
| 3 | [`spec/`](spec/) — prose specs, area by area | Approved 2026-10-31 (all 11 areas) |
| 4 | [`schemas/`](schemas/), [`conformance/`](conformance/) — schemas and fixtures, area by area | Complete 2026-11-02 (all 11 areas); post-Phase 4 review amendments 2026-11-07 to 2026-11-14. Pending Phase 5: EVAL-036 and the adapter requirements PROV-001–009, PROV-080, verified once native adapter transcripts ship |
| 5 | Codegen, CI, first published release | In progress: spec CI and the shared conformance runner ([`tools/`](tools/)) are in place; codegen and the first release are not |

Design notes feeding these phases live in [`notes/`](notes/). Notes are non-normative.

## What is normative

Only `domain.md`, accepted ADRs, the area specs, schemas, and conformance fixtures are binding. Where prose and fixtures disagree, one of them is corrected — never the implementation alone.

## Running conformance

An implementation provides a **driver** that speaks the driver protocol ([`conformance/schema/driver.yaml`](conformance/schema/driver.yaml)). The shared runner then runs the whole suite against it:

```
python tools/runner/run.py --driver "<command that starts your driver>" --report report.json --junit report.xml
```

The runner's report for a full-suite run is the conformance claim (EVAL-023, ADR-0020). See [`tools/README.md`](tools/README.md) for every tool in spec CI.

## Contributing

Review and scrutiny are welcome. Contributions require [Developer Certificate of Origin](https://developercertificate.org/) sign-off (`git commit -s`). Changes to intent, domain, ADRs, schemas, and fixtures require maintainer approval.

## License

[Apache-2.0](LICENSE)
