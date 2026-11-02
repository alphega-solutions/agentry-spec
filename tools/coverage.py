"""Check that every normative requirement is covered by a fixture (EVAL-010).

Coverage is enforced for the requirement prefixes listed in
conformance/coverage.yaml; other areas are reported only.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from common import ROOT, fixture_files, load_yaml, spec_requirements


def main() -> int:
    reqs = spec_requirements()
    config = load_yaml(ROOT / "conformance" / "coverage.yaml") or {}
    enforced = set(config.get("enforced", []))
    elsewhere = config.get("verifiedElsewhere") or {}
    unknown = sorted(r for r in elsewhere if r not in reqs)
    if unknown:
        print(f"coverage.yaml: verifiedElsewhere names unknown requirements: {', '.join(unknown)}")
        return 1

    covered: dict[str, list[str]] = defaultdict(list)
    for fx in fixture_files():
        doc = load_yaml(fx)
        for rid in doc.get("requirements", []):
            covered[rid].append(doc["id"])

    by_prefix: dict[str, list[str]] = defaultdict(list)
    for rid, info in reqs.items():
        if info["normative"] and not info["untestable"]:
            by_prefix[rid.split("-")[0]].append(rid)

    failed = False
    for prefix in sorted(by_prefix):
        ids = sorted(by_prefix[prefix])
        missing = [r for r in ids if r not in covered and r not in elsewhere]
        status = "ENFORCED" if prefix in enforced else "reported"
        print(f"{prefix:5} {len(ids) - len(missing):3}/{len(ids):3} covered  [{status}]")
        if prefix in enforced and missing:
            failed = True
            for r in missing:
                print(f"  MISSING {r}: {reqs[r]['text'][:90]}")
    for r, why in sorted(elsewhere.items()):
        print(f"  {r} verified elsewhere: {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
