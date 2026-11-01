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


CONFIG = "https://alphega.io/agentry/schemas/config"
KIND_SCHEMAS = {
    "PolicyBundle": f"{CONFIG}/policy-bundle/v1.json",
    "Persona": f"{CONFIG}/persona/v1.json",
    "HarnessProfile": f"{CONFIG}/harness-profile/v1.json",
    "Deployment": f"{CONFIG}/deployment/v1.json",
}
# Kinds whose schemas arrive with Areas 4-5; their artifacts are not yet validated.
PENDING_KINDS = {"Tool", "Hook"}
BEHAVIOURAL = ("PolicyBundle", "Persona", "HarnessProfile")
MERGE_RULES = {"union", "intersect", "min", "stricter", "locked", "override"}
# Envelope fields are not merged; extensions are vendor data.
UNMERGED = {"kind", "id", "version", "schemaVersion", "extensions"}
# The only paths allowed to use `override` (CFG-033): display labels, and
# adapter-declared generation parameters in the model block (PROV-022).
OVERRIDE_ALLOWLIST = {
    "Persona.displayName",
    "Persona.description",
    "PolicyBundle.model.params.*",
    "Persona.model.params.*",
    "HarnessProfile.model.params.*",
}


def check_shared_config(schemas: dict, reg) -> list[str]:
    errors: list[str] = []
    for path in sorted((ROOT / "conformance" / "shared").rglob("*.yaml")):
        rel = path.relative_to(ROOT)
        doc = load_yaml(path)
        kind = doc.get("kind") if isinstance(doc, dict) else None
        if kind in PENDING_KINDS:
            continue
        if kind not in KIND_SCHEMAS:
            errors.append(f"{rel}: unknown configuration kind {kind!r}")
            continue
        v = Draft202012Validator(schemas[KIND_SCHEMAS[kind]], registry=reg, format_checker=FormatChecker())
        for err in v.iter_errors(doc):
            errors.append(f"{rel}: {'/'.join(map(str, err.absolute_path))}: {err.message}")
    return errors


def _resolve(schemas: dict, base: str, node: dict) -> tuple[str, dict]:
    """Follow a node's $ref (if any) to (base id, target schema)."""
    ref = node.get("$ref")
    if not ref:
        return base, node
    doc_id, _, frag = ref.partition("#")
    doc_id = doc_id or base
    target = schemas[doc_id]
    for part in [p for p in frag.split("/") if p]:
        target = target[part]
    return _resolve(schemas, doc_id, target)


def check_merge_annotations(schemas: dict) -> list[str]:
    """Every behavioural field declares a merge rule; `stricter` declares an order;
    `override` only on allowlisted paths; deployments carry no merge annotations."""
    errors: list[str] = []

    def check_field(kind: str, path: str, base: str, node: dict) -> None:
        rule = node.get("x-agentry-merge")
        where = f"{kind}.{path}"
        if rule is None:
            rbase, target = _resolve(schemas, base, node)
            if "properties" in target and target.get("type", "object") == "object":
                walk_block(kind, path, rbase, target)  # a block merges field by field
            else:
                errors.append(f"merge: {where} has no x-agentry-merge (CFG-030)")
            return
        if rule not in MERGE_RULES:
            errors.append(f"merge: {where} has unknown x-agentry-merge {rule!r}")
        if rule == "stricter":
            order = node.get("x-agentry-order")
            if not isinstance(order, list) or len(order) < 2:
                errors.append(f"merge: {where} is stricter without an x-agentry-order (CFG-031)")
        if rule == "override" and where not in OVERRIDE_ALLOWLIST:
            errors.append(f"merge: {where} uses override; not in the CFG-033 allowlist")
        # Map-valued field: the value schema carries the per-key rules (CFG-030).
        rbase, target = _resolve(schemas, base, node)
        if isinstance(target.get("additionalProperties"), dict):
            check_field(kind, f"{path}.*", rbase, target["additionalProperties"])

    def walk_block(kind: str, prefix: str, base: str, schema: dict) -> None:
        for name, sub in schema.get("properties", {}).items():
            if name in UNMERGED:
                continue
            check_field(kind, f"{prefix}.{name}" if prefix else name, base, sub)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            check_field(kind, f"{prefix}.*", base, extra)

    for kind in BEHAVIOURAL:
        sid = KIND_SCHEMAS[kind]
        walk_block(kind, "", sid, schemas[sid])

    def no_merge(node, where: str) -> None:
        if isinstance(node, dict):
            if "x-agentry-merge" in node or "x-agentry-order" in node:
                errors.append(f"merge: {where} carries a merge annotation; deployments are not a behavioural layer (CFG-021)")
            for k, v in node.items():
                no_merge(v, f"{where}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                no_merge(v, f"{where}/{i}")

    no_merge(schemas[KIND_SCHEMAS["Deployment"]], "Deployment")
    return errors


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

    # 4. Shared configuration artifacts validate against their kind's schema.
    errors += check_shared_config(schemas, reg)

    # 5. Spec maintenance: merge annotations on configuration schemas (CFG-030, 031, 033).
    errors += check_merge_annotations(schemas)

    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(schemas)} schemas, {len(ids)} fixtures checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
