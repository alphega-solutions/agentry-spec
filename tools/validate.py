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
# Validator keywords whose default messages quote the offending value. Configuration may
# hold credentials pasted in by mistake, so errors describe the constraint and never the
# value: CI logs are public.
VALUE_ECHOING = {"pattern", "enum", "const", "type", "format", "minimum", "maximum",
                 "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
                 "multipleOf", "not", "oneOf", "anyOf", "if", "then", "else", "contains",
                 "uniqueItems", "minItems", "maxItems", "propertyNames", "dependentRequired",
                 "false"}


def describe(err) -> str:
    """A schema error message that names the constraint but never quotes the value."""
    path = "/".join(map(str, err.absolute_path)) or "(root)"
    kw = err.validator
    if kw in ("required", "additionalProperties", "unevaluatedProperties"):
        # These messages name property keys, not values.
        return f"{path}: {err.message}"
    if kw == "pattern":
        return f"{path}: does not match pattern {err.validator_value}"
    if kw == "enum":
        return f"{path}: is not one of {err.validator_value}"
    if kw == "const":
        return f"{path}: must equal {err.validator_value!r}"
    if kw == "type":
        return f"{path}: must be of type {err.validator_value}"
    if kw in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
              "minLength", "maxLength", "minItems", "maxItems", "multipleOf"):
        return f"{path}: violates {kw} {err.validator_value}"
    return f"{path}: fails `{kw}`"


KIND_SCHEMAS = {
    "PolicyBundle": f"{CONFIG}/policy-bundle/v1.json",
    "Persona": f"{CONFIG}/persona/v1.json",
    "HarnessProfile": f"{CONFIG}/harness-profile/v1.json",
    "Deployment": f"{CONFIG}/deployment/v1.json",
    "Tool": f"{CONFIG}/tool/v1.json",
}
# Kinds whose schemas arrive with Area 5; their artifacts are checked only
# against the interim names in conformance/shared/NAMES.md.
PENDING_KINDS = {"Hook"}
BEHAVIOURAL = ("PolicyBundle", "Persona", "HarnessProfile")
# Kinds that are not behavioural layers and carry no merge annotations (CFG-021, TOOL-001).
UNLAYERED = ("Deployment", "Tool")
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
    # The summarizer model (CTX-100) is `locked` as a whole; its params are the
    # same adapter-declared generation parameters.
    "PolicyBundle.context.compaction.model.params.*",
    "HarnessProfile.context.compaction.model.params.*",
}


SECRET_REF = "https://alphega.io/agentry/schemas/config/defs/v1.json#/$defs/secretRef"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
REF_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}@[1-9][0-9]*$")
SECRET_PATTERN = re.compile(r"^secret://[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$")

# Canonical strictness orders, strictest first: CFG-031 as amended by Areas 5,
# 6 and 7 (HOOK-104, HITL-023, HITL-081, CTX-102). Paths are `Kind.field`,
# with `*` for a map key. Every `stricter` field in a configuration schema must
# be listed here with exactly this order, and every listed path in a schema'd
# behavioural kind must exist. Tool fields with these values (approval,
# onTainted, onTaintedEgress) are not merged, so they are not listed; the
# Hook failure mode lists its paths when the Area 5 schema lands.
STRICTNESS_ORDERS = [
    # (family, order, paths)
    ("Hook failure mode", ["failClosed", "failOpen"], []),  # Hook schema (Area 5)
    ("Delivery mode", ["buffered", "streamed"], ["HarnessProfile.deliveryMode"]),
    ("Taint outcome", ["block", "escalate", "allow"], ["PolicyBundle.toolTaintDefaults.*"]),
    ("Approval policy", ["always", "policy", "never"], ["PolicyBundle.sensitivityPolicies.*.approval"]),
    ("Checkpoint granularity", ["tool", "turn"], ["HarnessProfile.checkpoint"]),
    ("Include reasoning in traces", [False, True], ["HarnessProfile.trace.includeReasoning"]),
    ("Deterministic guardrails (HOOK-104)", [True, False],
     ["PolicyBundle.guardrails.requireDeterministic", "HarnessProfile.guardrails.requireDeterministic"]),
    ("Self-approval (HITL-023)", [False, True], ["PolicyBundle.allowSelfApproval.*"]),
    ("Expiry of undecided actions (HITL-081)", ["close", "reject"], ["HarnessProfile.onExpiry"]),
    ("Compaction mode (CTX-102)", ["none", "truncate", "summarize"],
     ["PolicyBundle.context.compaction.mode", "HarnessProfile.context.compaction.mode"]),
    ("Automatic retrieval (CTX-102)", [False, True],
     ["PolicyBundle.context.retrieval.auto", "HarnessProfile.context.retrieval.auto"]),
]
CANONICAL_ORDER = {path: order for _, order, paths in STRICTNESS_ORDERS for path in paths}

# Interim Hook names (conformance/shared/NAMES.md) until the Area 5 schema exists.
# Tool names are normative in schemas/config/v1/tool.yaml.
HOOK_SOURCES = {
    "rule": ["when", "then"],
    "native": ["handler"],
    "remote": ["endpoint"],
    "model": ["model", "instructions", "maxTokens"],
}
# Fields whose value is an ID declared elsewhere (deployment or registry), not a URI.
ID_FIELDS = {"handler", "endpoint"}


def _check_pending(art: dict) -> list[str]:
    """Minimal check of a Hook artifact against NAMES.md."""
    key, table = "source", HOOK_SOURCES
    block = art.get(key)
    if not isinstance(block, dict):
        return [f"{key}: missing or not an object (NAMES.md)"]
    bkind = block.get("kind")
    if bkind not in table:
        return [f"{key}.kind: unknown {bkind!r}; expected one of {sorted(table)} (NAMES.md)"]
    problems: list[str] = []
    fields = table[bkind]
    for f in fields:
        if f not in block:
            problems.append(f"{key}: kind {bkind} requires `{f}` (NAMES.md)")
    for f in block:
        if f not in fields and f not in ("kind", "credentials"):
            problems.append(f"{key}: unknown field `{f}` for kind {bkind} (NAMES.md)")
    for f in ID_FIELDS & set(fields):
        v = block.get(f)
        if v is not None and not (isinstance(v, str) and ID_PATTERN.match(v)):
            problems.append(f"{key}.{f}: {v!r} is not an ID (NAMES.md)")
    creds = block.get("credentials")
    if creds is not None:
        if not isinstance(creds, dict):
            problems.append(f"{key}.credentials: must be a map of names to secret references")
        else:
            if not all(isinstance(ref, str) and SECRET_PATTERN.match(ref) for ref in creds.values()):
                problems.append(f"{key}.credentials: every entry must be a secret reference (CFG-061)")
    if bkind == "rule" and isinstance(block.get("then"), dict):
        then = block["then"]
        result = then.get("result")
        need = {"annotate": "labels", "block": "reasonCode", "escalate": "reasonCode"}.get(result)
        if need is None:
            problems.append(f"source.then.result: unknown {result!r} (HOOK-090)")
        elif need not in then:
            problems.append(f"source.then: result {result} requires `{need}` (HOOK-090)")
    if bkind == "model" and isinstance(block.get("model"), dict):
        for f in ("provider", "name"):
            if f not in block["model"]:
                problems.append(f"source.model: requires `{f}`")
    return problems


def check_shared_config(schemas: dict, reg) -> list[str]:
    errors: list[str] = []
    for path in sorted((ROOT / "conformance" / "shared").rglob("*.yaml")):
        rel = path.relative_to(ROOT)
        doc = load_yaml(path)
        kind = doc.get("kind") if isinstance(doc, dict) else None
        if kind in PENDING_KINDS:
            errors += [f"{rel}: {e}" for e in _check_pending(doc)]
            continue
        if kind not in KIND_SCHEMAS:
            errors.append(f"{rel}: unknown configuration kind {kind!r}")
            continue
        v = Draft202012Validator(schemas[KIND_SCHEMAS[kind]], registry=reg, format_checker=FormatChecker())
        for err in v.iter_errors(doc):
            errors.append(f"{rel}: {describe(err)}")
    return errors


def _deref(schemas: dict, base: str, ref: str) -> tuple[str, str, dict]:
    """Resolve one $ref to (canonical uri, base id, target schema)."""
    doc_id, _, frag = ref.partition("#")
    doc_id = doc_id or base
    target = schemas[doc_id]
    for part in [p for p in frag.split("/") if p]:
        target = target[part]
    return f"{doc_id}#{frag}", doc_id, target


def _resolve(schemas: dict, base: str, node: dict) -> tuple[str, dict]:
    """Follow a node's $ref chain (if any) to (base id, target schema)."""
    ref = node.get("$ref")
    if not ref:
        return base, node
    _, doc_id, target = _deref(schemas, base, ref)
    return _resolve(schemas, doc_id, target)


def _ref_chain(schemas: dict, base: str, node: dict) -> list[str]:
    chain: list[str] = []
    while isinstance(node, dict) and node.get("$ref") and len(chain) < 32:
        uri, base, node = _deref(schemas, base, node["$ref"])
        chain.append(uri)
    return chain


def _expand(schemas: dict, base: str, node: dict, depth: int = 0) -> list[tuple[str, dict]]:
    """The node plus every schema it composes: $ref targets and allOf/anyOf/oneOf members."""
    if depth > 32 or not isinstance(node, dict):
        return []
    out = [(base, node)]
    if node.get("$ref"):
        _, rbase, target = _deref(schemas, base, node["$ref"])
        out += _expand(schemas, rbase, target, depth + 1)
    for kw in ("allOf", "anyOf", "oneOf"):
        for sub in node.get(kw, []) or []:
            out += _expand(schemas, base, sub, depth + 1)
    return out


def _shape(parts: list[tuple[str, dict]]):
    """Merged named properties, additionalProperties and items of composed parts."""
    props: dict[str, tuple[str, dict]] = {}
    addl = None
    items: list[tuple[str, dict]] = []
    for b, p in parts:
        for name, sub in (p.get("properties") or {}).items():
            props.setdefault(name, (b, sub))
        if isinstance(p.get("additionalProperties"), dict) and addl is None:
            addl = (b, p["additionalProperties"])
        if isinstance(p.get("items"), dict):
            items.append((b, p["items"]))
    return props, addl, items


def check_merge_annotations(schemas: dict) -> list[str]:
    """CFG-030, 031, 033 on the behavioural schemas.

    - every field declares x-agentry-merge, or is a block whose fields do;
      a `union` map annotates each value (additionalProperties or named
      properties) with its own rule;
    - annotations are checked wherever they appear: array items,
      allOf/anyOf/oneOf members and $ref targets included;
    - each `stricter` field's x-agentry-order lists exactly the field's enum
      values (or both booleans) and equals the canonical order in
      STRICTNESS_ORDERS; x-agentry-order appears only with `stricter`;
    - `override` only on allowlisted paths;
    - a field path declared by more than one kind has the same rule in each;
    - deployments and tools, including everything they reference, carry no
      annotations.
    """
    errors: list[str] = []
    rules_by_path: dict[str, dict[str, str]] = {}
    seen_paths: set[str] = set()

    def validate(kind: str, path: str, rule: str, parts) -> None:
        where = f"{kind}.{path}"
        if rule not in MERGE_RULES:
            errors.append(f"merge: {where} has unknown x-agentry-merge {rule!r}")
        orders = [p["x-agentry-order"] for _, p in parts if "x-agentry-order" in p]
        if rule != "stricter":
            if orders:
                errors.append(f"merge: {where} has x-agentry-order but rule {rule!r}")
        else:
            order = orders[0] if orders else None
            if not isinstance(order, list) or len(order) < 2:
                errors.append(f"merge: {where} is stricter without an x-agentry-order (CFG-031)")
            else:
                enums = [p["enum"] for _, p in parts if "enum" in p]
                is_bool = any(p.get("type") == "boolean" for _, p in parts)
                if enums:
                    if len(order) != len(set(map(repr, order))) or {repr(x) for x in order} != {repr(x) for x in enums[0]}:
                        errors.append(f"merge: {where} x-agentry-order {order} does not list exactly the enum {enums[0]}")
                elif is_bool:
                    if order not in ([True, False], [False, True]) or any(type(x) is not bool for x in order):
                        errors.append(f"merge: {where} x-agentry-order {order} must be [true, false] or [false, true]")
                else:
                    errors.append(f"merge: {where} is stricter but has neither an enum nor boolean type")
                canonical = CANONICAL_ORDER.get(where)
                if canonical is None:
                    errors.append(f"merge: {where} is stricter but not in the canonical STRICTNESS_ORDERS table (CFG-031)")
                elif order != canonical or any(type(a) is not type(b) for a, b in zip(order, canonical)):
                    errors.append(f"merge: {where} x-agentry-order {order} differs from canonical {canonical} (CFG-031)")
        if rule == "override" and where not in OVERRIDE_ALLOWLIST:
            errors.append(f"merge: {where} uses override; not in the CFG-033 allowlist")
        rules_by_path.setdefault(path, {})[kind] = rule

    def visit(kind: str, path: str, base: str, node: dict, required: bool, depth: int = 0) -> None:
        if depth > 32:
            return
        parts = _expand(schemas, base, node)
        rules = {p["x-agentry-merge"] for _, p in parts if "x-agentry-merge" in p}
        props, addl, items = _shape(parts)
        is_block = not rules and (bool(props) or addl is not None)
        if len(rules) > 1:
            errors.append(f"merge: {kind}.{path} has conflicting x-agentry-merge {sorted(rules)}")
        elif rules:
            seen_paths.add(f"{kind}.{path}")
            validate(kind, path, next(iter(rules)), parts)
        elif any("x-agentry-order" in p for _, p in parts):
            errors.append(f"merge: {kind}.{path} has x-agentry-order without x-agentry-merge")
        if required and not rules and not is_block:
            errors.append(f"merge: {kind}.{path} has no x-agentry-merge (CFG-030)")
        # Children of a block, and the values of a `union` map, carry their own rules.
        child_required = required and (is_block or rules == {"union"})
        prefix = f"{path}." if path else ""
        for name, (b, sub) in props.items():
            if name in UNMERGED:
                continue
            visit(kind, f"{prefix}{name}", b, sub, child_required, depth + 1)
        if addl is not None:
            visit(kind, f"{prefix}*", addl[0], addl[1], child_required, depth + 1)
        for b, sub in items:  # array elements merge as wholes; audit only
            visit(kind, f"{path}[]", b, sub, False, depth + 1)

    for kind in BEHAVIOURAL:
        sid = KIND_SCHEMAS[kind]
        visit(kind, "", sid, schemas[sid], True)

    for path, by_kind in sorted(rules_by_path.items()):
        if len(set(by_kind.values())) > 1:
            detail = ", ".join(f"{k}: {r}" for k, r in sorted(by_kind.items()))
            errors.append(f"merge: field path {path} has different merge rules across kinds ({detail}) (CFG-070 as amended)")
    for path in sorted(CANONICAL_ORDER):
        if path.split(".")[0] in BEHAVIOURAL and path not in seen_paths:
            errors.append(f"merge: STRICTNESS_ORDERS lists {path}, which no schema declares")

    def no_merge(kind: str, base: str, node, where: str, seen: set) -> None:
        if isinstance(node, dict):
            if "x-agentry-merge" in node or "x-agentry-order" in node:
                errors.append(f"merge: {where} carries a merge annotation; {kind} is not a behavioural layer (CFG-021)")
            if isinstance(node.get("$ref"), str):
                uri, rbase, target = _deref(schemas, base, node["$ref"])
                if uri not in seen:
                    no_merge(kind, rbase, target, f"{where}->{uri}", seen | {uri})
            for k, v in node.items():
                no_merge(kind, base, v, f"{where}/{k}", seen)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                no_merge(kind, base, v, f"{where}/{i}", seen)

    for kind in UNLAYERED:
        sid = KIND_SCHEMAS[kind]
        no_merge(kind, sid, schemas[sid], kind, {sid + "#"})
    return errors


def check_reference_markers(schemas: dict) -> list[str]:
    """CFG-060, 061: a schema node is a secretRef (directly or by $ref chain)
    exactly when it carries `x-agentry-secret: true`."""
    errors: list[str] = []

    def walk(sid: str, node, where: str) -> None:
        if isinstance(node, dict):
            if "x-agentry-secret" in node and node["x-agentry-secret"] is not True:
                errors.append(f"secret: {where} has an x-agentry-secret value other than `true`")
            is_secret = SECRET_REF in _ref_chain(schemas, sid, node)
            marked = node.get("x-agentry-secret") is True
            if is_secret and not marked:
                errors.append(f"secret: {where} is a secret reference without x-agentry-secret: true (CFG-061)")
            if marked and not is_secret:
                errors.append(f"secret: {where} has x-agentry-secret: true but is not a secretRef (CFG-061)")
            for k, v in node.items():
                walk(sid, v, f"{where}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(sid, v, f"{where}/{i}")

    for sid, doc in schemas.items():
        walk(sid, doc, sid)
    return errors


def _override_problems(schemas: dict, value, base: str, node: dict, pointer: str) -> list[str]:
    """Run-request overrides use harness profile field paths (CFG-101 as amended)."""
    if not isinstance(value, dict):
        return [f"overrides{pointer or '/'}: must be an object of profile fields"]
    props, addl, _ = _shape(_expand(schemas, base, node))
    problems: list[str] = []
    for key, v in value.items():
        ptr = f"{pointer}/{str(key).replace('~', '~0').replace('/', '~1')}"
        if key in props and key not in UNMERGED:
            b, sub = props[key]
        elif addl is not None:
            b, sub = addl
        else:
            problems.append(f"overrides{ptr}: not a harness profile field path (CFG-101)")
            continue
        parts = _expand(schemas, b, sub)
        annotated = any("x-agentry-merge" in p for _, p in parts)
        sub_props, sub_addl, _ = _shape(parts)
        if not annotated and (sub_props or sub_addl is not None):
            problems += _override_problems(schemas, v, b, sub, ptr)
    return problems


def _base_refs(base: str) -> set[str] | None:
    d = ROOT / "conformance" / "shared" / base
    if not d.is_dir():
        return None
    refs = set()
    for p in d.glob("*.yaml"):
        doc = load_yaml(p)
        if isinstance(doc, dict) and "id" in doc and "version" in doc:
            refs.add(f"{doc['id']}@{doc['version']}")
    return refs


def check_inline_config(doc: dict, schemas: dict, reg) -> list[str]:
    """Inline configuration that is expected to load must be schema-valid.

    Artifacts in setup.config.artifacts, and in `load` steps expected to
    succeed, are validated against their kind's schema (Hook against the
    interim names in NAMES.md). Artifacts in steps expected to fail are
    not, since they may be invalid on purpose. Run-request `overrides` must use
    harness profile field paths, and `remove` must name artifacts present in
    the base or previous set when that set is known.
    """
    problems: list[str] = []

    def check(art: dict, where: str) -> None:
        kind = art.get("kind")
        if kind in PENDING_KINDS:
            problems.extend(f"{where} {kind} {art.get('id')}@{art.get('version')}: {e}" for e in _check_pending(art))
            return
        if kind not in KIND_SCHEMAS:
            problems.append(f"{where}: unknown configuration kind {kind!r}")
            return
        v = Draft202012Validator(schemas[KIND_SCHEMAS[kind]], registry=reg, format_checker=FormatChecker())
        for err in v.iter_errors(art):
            problems.append(f"{where} {kind} {art.get('id')}@{art.get('version')}: {describe(err)}")

    def refs_of(arts) -> set[str]:
        return {f"{a.get('id')}@{a.get('version')}" for a in arts or [] if isinstance(a, dict)}

    setup_cfg = (doc.get("setup") or {}).get("config") or {}
    for i, art in enumerate(setup_cfg.get("artifacts", []) or []):
        check(art, f"setup.config.artifacts[{i}]")

    current = _base_refs(setup_cfg.get("base", "")) if setup_cfg.get("base") else None
    if current is not None:
        for ref in setup_cfg.get("remove", []) or []:
            if ref not in current:
                problems.append(f"setup.config.remove: {ref} is not in base {setup_cfg['base']!r}")
        current = (current | refs_of(setup_cfg.get("artifacts"))) - set(setup_cfg.get("remove", []) or [])

    profile_id = KIND_SCHEMAS["HarnessProfile"]

    def check_overrides(step: dict, where: str) -> None:
        if "concurrently" in step:
            for k, sub in enumerate(step["concurrently"]):
                check_overrides(sub, f"{where}.concurrently[{k}]")
        if "overrides" in step:
            problems.extend(f"{where}: {e}" for e in
                            _override_problems(schemas, step["overrides"], profile_id, schemas[profile_id], ""))

    for i, step in enumerate(doc.get("script", []) or []):
        check_overrides(step, f"script[{i}]")
        if "load" not in step:
            continue
        load = step["load"] or {}
        ok = (step.get("expect") or {}).get("ok")
        for ref in load.get("remove", []) or []:
            if not REF_PATTERN.match(str(ref)):
                problems.append(f"script[{i}].load.remove: {ref!r} is not id@version")
            elif current is not None and ref not in current:
                problems.append(f"script[{i}].load.remove: {ref} is not in the configuration in force")
        if ok is True:
            for j, art in enumerate(load.get("artifacts", []) or []):
                check(art, f"script[{i}].load.artifacts[{j}]")
            if current is not None:
                current = (current | refs_of(load.get("artifacts"))) - set(load.get("remove", []) or [])
        elif ok is None:
            current = None  # outcome unknown: later removals are not determinable
    return problems


def _base_artifacts(base: str) -> dict | None:
    d = ROOT / "conformance" / "shared" / base
    if not d.is_dir():
        return None
    arts = {}
    for p in sorted(d.glob("*.yaml")):
        doc = load_yaml(p)
        if isinstance(doc, dict) and "kind" in doc:
            arts[(doc.get("kind"), doc.get("id"), doc.get("version"))] = doc
    return arts


def _apply(arts: dict, add, remove) -> dict:
    out = dict(arts)
    for a in add or []:
        if isinstance(a, dict):
            out[(a.get("kind"), a.get("id"), a.get("version"))] = a
    for ref in remove or []:
        rid, _, ver = str(ref).partition("@")
        for k in [k for k in out if k[1] == rid and str(k[2]) == ver]:
            del out[k]
    return out


def _native(arts: dict) -> list[tuple[str, str]]:
    found = []
    for a in arts.values():
        b = a.get("binding") if a.get("kind") == "Tool" else None
        if isinstance(b, dict) and b.get("kind") == "native" and isinstance(b.get("handler"), str):
            found.append((str(a.get("id")), b["handler"]))
    return sorted(found)


def check_handlers(doc: dict) -> list[str]:
    """Native bindings resolve to registered handlers (TOOL-010, fixture `setup.handlers`).

    By default every native handler is registered except names beginning
    `unregistered.`; `setup.handlers`, when given, restricts registration to
    exactly those names. A handler that is not registered may appear only in a
    load expected to fail, which is how fixtures test an unresolved binding.
    """
    setup = doc.get("setup") or {}
    cfg = setup.get("config") or {}
    arts = _base_artifacts(cfg.get("base", "")) if cfg.get("base") else None
    if arts is None:
        return []
    arts = _apply(arts, cfg.get("artifacts"), cfg.get("remove"))
    configs = [("setup.config", arts, True)]
    current = arts
    for i, step in enumerate(doc.get("script", []) or []):
        if "load" not in step:
            continue
        load = step["load"] or {}
        nxt = _apply(current, load.get("artifacts"), load.get("remove"))
        ok = (step.get("expect") or {}).get("ok")
        configs.append((f"script[{i}].load", nxt, ok is not False))
        if ok is True:
            current = nxt
    explicit = set(setup["handlers"]) if "handlers" in setup else None

    def registered(h: str) -> bool:
        if h.startswith("unregistered."):
            return False
        return explicit is None or h in explicit

    problems = []
    for where, a, must in configs:
        for tid, h in _native(a):
            if must and not registered(h):
                problems.append(f"{where}: native handler {h} of tool {tid} is not registered "
                                f"(setup.handlers, TOOL-010)")
    return sorted(set(problems))


def check_matchers(doc: dict) -> list[str]:
    """`$count` is well formed; `$not` never wraps `$contains` (use `$count`)."""
    problems: list[str] = []

    def walk(v, path: str) -> None:
        if isinstance(v, dict):
            if "$count" in v:
                c = v["$count"]
                bounds = [k for k in ("equals", "gte", "lte") if isinstance(c, dict) and k in c]
                if (not isinstance(c, dict) or "of" not in c or len(bounds) != 1
                        or set(c) - {"of", "equals", "gte", "lte"}
                        or not (isinstance(c[bounds[0]], int) and c[bounds[0]] >= 0)):
                    problems.append(f"{path}: $count must be {{of: m, equals|gte|lte: n}} with exactly one bound")
            if "$not" in v and isinstance(v["$not"], dict) and "$contains" in v["$not"]:
                problems.append(f"{path}: $not around $contains; use $count")
            for k, x in v.items():
                walk(x, f"{path}/{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{path}/{i}")

    walk(doc.get("expect"), "expect")
    for i, step in enumerate(doc.get("script", []) or []):
        walk(step.get("expect"), f"script[{i}].expect")
    return problems


def check_stub_call_keys(doc: dict) -> list[str]:
    """`expect.stubCalls` keys name a stub: a native tool ID, `<server>/<tool>`,
    `<endpoint>/<operation>`, or a remote hook ID."""
    calls = (doc.get("expect") or {}).get("stubCalls") or {}
    if not calls:
        return []
    setup = doc.get("setup") or {}
    stubs = setup.get("stubs") or {}
    valid = set(stubs.get("tools") or {}) | set(stubs.get("remoteHooks") or {})
    for srv, server in (stubs.get("mcpServers") or {}).items():
        names = set((server or {}).get("tools") or {})
        for change in (server or {}).get("changes") or []:
            names |= set(change.get("tools") or {})
        valid |= {f"{srv}/{t}" for t in names}
    for ep, ops in (stubs.get("httpEndpoints") or {}).items():
        valid |= {f"{ep}/{op}" for op in (ops or {})}
    cfg = setup.get("config") or {}
    arts = _base_artifacts(cfg.get("base", "")) if cfg.get("base") else {}
    arts = _apply(arts or {}, cfg.get("artifacts"), cfg.get("remove"))
    for step in doc.get("script", []) or []:
        if "load" in step:
            arts = _apply(arts, (step["load"] or {}).get("artifacts"), (step["load"] or {}).get("remove"))
    explicit = set(setup["handlers"]) if "handlers" in setup else None
    valid |= {tid for tid, h in _native(arts)
              if not h.startswith("unregistered.") and (explicit is None or h in explicit)}
    return [f"expect.stubCalls: {k} names no stub (tool ID, <server>/<tool>, <endpoint>/<operation> or remote hook ID)"
            for k in calls if k not in valid]


def check_crashes(doc: dict) -> list[str]:
    """A crash step arms a crash for a later action step on its session."""
    problems: list[str] = []
    script = doc.get("script", []) or []
    for i, step in enumerate(script):
        if "crash" not in step:
            continue
        target = (step["crash"] or {}).get("session")
        for later in script[i + 1:]:
            if "action" in later and (target is None or target in (later.get("session"), later.get("bind"))):
                break
        else:
            problems.append(f"script[{i}]: crash has no later action step on {target or 'any session'}")
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
            errors.append(f"{ex}: expected valid, got: {describe(errs[0])}")
        if kind == "invalid" and not errs:
            errors.append(f"{ex}: expected invalid, but it validated")

    # 3. Fixtures validate against the fixture format and cite real requirements.
    reqs = spec_requirements()
    ids: set[str] = set()
    for fx in fixture_files():
        doc = load_yaml(fx)
        target = CEL_ID if str(doc.get("id", "")).startswith("cel.") else FIXTURE_ID
        for err in validator(target).iter_errors(doc):
            errors.append(f"{fx.relative_to(ROOT)}: {describe(err)}")
        fid = doc.get("id")
        if fid in ids:
            errors.append(f"{fx.relative_to(ROOT)}: duplicate fixture id {fid}")
        ids.add(fid)
        for rid in doc.get("requirements", []):
            if rid not in reqs:
                errors.append(f"{fx.relative_to(ROOT)}: unknown requirement {rid}")
        if target == FIXTURE_ID:
            errors += [f"{fx.relative_to(ROOT)}: {e}" for e in check_placeholders(doc)]
            errors += [f"{fx.relative_to(ROOT)}: {e}" for e in check_inline_config(doc, schemas, reg)]
            errors += [f"{fx.relative_to(ROOT)}: {e}" for e in check_handlers(doc)]
            errors += [f"{fx.relative_to(ROOT)}: {e}" for e in check_matchers(doc)]
            errors += [f"{fx.relative_to(ROOT)}: {e}" for e in check_crashes(doc)]
            errors += [f"{fx.relative_to(ROOT)}: {e}" for e in check_stub_call_keys(doc)]

    # 4. Shared configuration artifacts validate against their kind's schema.
    errors += check_shared_config(schemas, reg)

    # 5. Spec maintenance: merge annotations on configuration schemas (CFG-030, 031, 033).
    errors += check_merge_annotations(schemas)

    # 6. Spec maintenance: secret fields are exactly the secretRef fields (CFG-060, 061).
    errors += check_reference_markers(schemas)

    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(schemas)} schemas, {len(ids)} fixtures checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
