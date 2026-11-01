"""Shared helpers for agentry-spec tooling."""
from __future__ import annotations

import pathlib
import re

import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_DIRS = [ROOT / "schemas", ROOT / "conformance" / "schema"]
REQ_DEF = re.compile(r"^- \*\*([A-Z]+-\d{3})\*\*(.*)$")


def load_yaml(path: pathlib.Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def schema_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for d in SCHEMA_DIRS:
        files += [p for p in sorted(d.rglob("*.yaml")) if "examples" not in p.parts]
    return files


def load_schemas() -> dict[str, dict]:
    schemas: dict[str, dict] = {}
    for path in schema_files():
        doc = load_yaml(path)
        sid = doc.get("$id")
        if not sid:
            raise SystemExit(f"{path}: missing $id")
        if sid in schemas:
            raise SystemExit(f"{path}: duplicate $id {sid}")
        schemas[sid] = doc
    return schemas


def registry(schemas: dict[str, dict]) -> Registry:
    return Registry().with_resources(
        (sid, Resource.from_contents(doc, default_specification=DRAFT202012))
        for sid, doc in schemas.items()
    )


def spec_requirements() -> dict[str, dict]:
    """Requirement ID -> {file, normative, untestable, text}.

    A requirement's block runs from its "- **ID**" line to the next requirement,
    heading, table, or blank line followed by non-indented text. It is normative
    if any line in the block contains **MUST (including sub-bullets).
    """
    reqs: dict[str, dict] = {}
    for path in sorted((ROOT / "spec").glob("[0-9]*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            m = REQ_DEF.match(lines[i].strip())
            if not m:
                i += 1
                continue
            rid, first = m.group(1), m.group(2)
            block = [first]
            j = i + 1
            while j < len(lines):
                ln = lines[j]
                if REQ_DEF.match(ln.strip()) or ln.startswith("#") or ln.startswith("|"):
                    break
                if ln.strip() == "" and j + 1 < len(lines) and lines[j + 1] and not lines[j + 1].startswith(" "):
                    break
                if ln.startswith("  "):
                    block.append(ln.strip())
                j += 1
            text = " ".join(block)
            if rid not in reqs:  # first definition wins; amendments only reference IDs
                reqs[rid] = {
                    "file": path.name,
                    "normative": "**MUST" in text,
                    "untestable": "*(untestable)*" in text,
                    "text": first.strip(),
                }
            i = j
    return reqs


def fixture_files() -> list[pathlib.Path]:
    base = ROOT / "conformance"
    out = []
    for p in sorted(base.rglob("*.yaml")):
        rel = p.relative_to(base).parts
        if rel[0] in ("schema", "shared") or p.name == "coverage.yaml":
            continue
        out.append(p)
    return out
