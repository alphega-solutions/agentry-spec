"""Publish schemas and fixtures as JSON under dist/ (ADR-0001)."""
from __future__ import annotations

import json
import shutil

from common import ROOT, load_yaml

DIST = ROOT / "dist"


def main() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    for src_dir in ("schemas", "conformance"):
        for path in sorted((ROOT / src_dir).rglob("*.yaml")):
            out = DIST / path.relative_to(ROOT).with_suffix(".json")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(load_yaml(path), indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {sum(1 for _ in DIST.rglob('*.json'))} JSON files to dist/")


if __name__ == "__main__":
    main()
