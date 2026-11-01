"""Validate schemas, schema examples, and conformance fixtures.

Exit status is non-zero on any failure.
"""
from __future__ import annotations

import re
import sys

from jsonschema import Draft202012Validator, FormatChecker

from common import ROOT, fixture_files, load_schemas, load_yaml, registry, spec_requirements

FIXTURE_ID = "https://alphega.io/agentry/schemas/conformance/fixture/v1.json"
CEL_ID = "https://alphega.io/agentry/schemas/conformance/cel-fixture/v1.json"


PLACEHOLDER = re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*$")


def _placeholders(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str) and PLACEHOLDER.match(value):
        found.add(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and PLACEHOLDER.match(k):
                found.add(k)
            found |= _placeholders(v)
    elif isinstance(value, list):
        for v in value:
            found |= _placeholders(v)
    return found


def check_placeholders(doc: dict) -> list[str]:
    """A placeholder used in a step must be bound by an earlier step's bind or capture."""
    problems: list[str] = []
    bound: set[str] = set()

    def visit(step: dict, idx: str) -> None:
        if "concurrently" in step:
            for k, sub in enumerate(step["concurrently"]):
                visit(sub, f"{idx}.{k}")
            return
        used = set()
        for key, val in step.items():
            if key in ("bind", "capture", "expect"):
                continue
            used |= _placeholders(val)
        for ph in sorted(used - bound):
            problems.append(f"script[{idx}] uses {ph} before it is bound")
        if isinstance(step.get("bind"), str):
            bound.add(step["bind"])
        for cap in step.get("capture", []) or []:
            bound.update(cap.get("bind", {}).values())

    for i, step in enumerate(doc.get("script", [])):
        visit(step, str(i))
    return problems


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
        if target == FIXTURE_ID:
            errors += [f"{fx.relative_to(ROOT)}: {e}" for e in check_placeholders(doc)]

    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(schemas)} schemas, {len(ids)} fixtures checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
