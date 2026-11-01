"""Validate schemas, schema examples, and conformance fixtures.

Exit status is non-zero on any failure.
"""
from __future__ import annotations

import sys

from jsonschema import Draft202012Validator, FormatChecker

from common import ROOT, fixture_files, load_schemas, load_yaml, registry, spec_requirements

FIXTURE_ID = "https://alphega.io/agentry/schemas/conformance/fixture/v1.json"
CEL_ID = "https://alphega.io/agentry/schemas/conformance/cel-fixture/v1.json"


def main() -> int:
    errors: list[str] = []
    schemas = load_schemas()
    reg = registry(schemas)

    # 1. Every schema is a valid draft 2020-12 schema with a conventional $id.
    for sid, doc in schemas.items():
        try:
            Draft202012Validator.check_schema(doc)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"schema {sid}: {exc}")
        if not sid.startswith("https://alphega.io/agentry/schemas/"):
            errors.append(f"schema {sid}: $id outside https://alphega.io/agentry/schemas/")

    def validator(sid: str) -> Draft202012Validator:
        return Draft202012Validator(schemas[sid], registry=reg, format_checker=FormatChecker())

    # 2. Schema examples: examples/valid/* must pass, examples/invalid/* must fail.
    for ex in sorted((ROOT / "schemas").rglob("examples/*/*.yaml")):
        doc = load_yaml(ex)
        target, instance = doc["schema"], doc["instance"]
        if target.split("#")[0] not in schemas:
            errors.append(f"{ex}: unknown schema {target}")
            continue
        wrapper = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": target}
        v = Draft202012Validator(wrapper, registry=reg, format_checker=FormatChecker())
        errs = list(v.iter_errors(instance))
        kind = ex.parent.name
        if kind == "valid" and errs:
            errors.append(f"{ex}: expected valid, got: {errs[0].message}")
        if kind == "invalid" and not errs:
            errors.append(f"{ex}: expected invalid, but it validated")

    # 3. Fixtures validate against the fixture format and cite real requirements.
    reqs = spec_requirements()
    ids: set[str] = set()
    for fx in fixture_files():
        doc = load_yaml(fx)
        target = CEL_ID if str(doc.get("id", "")).startswith("cel.") else FIXTURE_ID
        for err in validator(target).iter_errors(doc):
            errors.append(f"{fx.relative_to(ROOT)}: {'/'.join(map(str, err.absolute_path))}: {err.message}")
        fid = doc.get("id")
        if fid in ids:
            errors.append(f"{fx.relative_to(ROOT)}: duplicate fixture id {fid}")
        ids.add(fid)
        for rid in doc.get("requirements", []):
            if rid not in reqs:
                errors.append(f"{fx.relative_to(ROOT)}: unknown requirement {rid}")

    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(schemas)} schemas, {len(ids)} fixtures checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
