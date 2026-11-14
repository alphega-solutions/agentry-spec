"""Check that every normative requirement is covered by a fixture (EVAL-010).

Coverage is enforced for the requirement prefixes listed in
conformance/coverage.yaml; other areas are reported only.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from common import ROOT, fixture_files, load_yaml, spec_requirements


def fixture_docs() -> list[dict]:
    return [load_yaml(fx) for fx in fixture_files()]


def main() -> int:
    reqs = spec_requirements()
    config = load_yaml(ROOT / "conformance" / "coverage.yaml") or {}
    enforced = set(config.get("enforced", []))
    elsewhere = config.get("verifiedElsewhere") or {}
    pending = config.get("pending") or {}
    unknown = sorted(r for r in [*elsewhere, *pending] if r not in reqs)
    if unknown:
        print(f"coverage.yaml: names unknown requirements: {', '.join(unknown)}")
        return 1

    covered: dict[str, list[str]] = defaultdict(list)
    for doc in fixture_docs():
        for rid in doc.get("requirements", []):
            covered[rid].append(doc["id"])

    by_prefix: dict[str, list[str]] = defaultdict(list)
    for rid, info in reqs.items():
        if info["normative"] and not info["untestable"]:
            by_prefix[rid.split("-")[0]].append(rid)

    failed = False
    for prefix in sorted(by_prefix):
        ids = sorted(by_prefix[prefix])
        # A pending requirement stays open even when fixtures cite it: its
        # fixtures cannot yet verify it (e.g. adapter cases before transcripts).
        open_ = [r for r in ids if (r not in covered and r not in elsewhere) or r in pending]
        missing = [r for r in open_ if r not in pending]
        status = "ENFORCED" if prefix in enforced else "reported"
        note = f", {len(open_) - len(missing)} pending" if len(open_) > len(missing) else ""
        print(f"{prefix:5} {len(ids) - len(open_):3}/{len(ids):3} covered{note}  [{status}]")
        if prefix in enforced and missing:
            failed = True
            for r in missing:
                print(f"  MISSING {r}: {reqs[r]['text'][:90]}")
    for r, why in sorted(elsewhere.items()):
        print(f"  {r} verified elsewhere: {why}")
    for r, why in sorted(pending.items()):
        print(f"  {r} PENDING: {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
