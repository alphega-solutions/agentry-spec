"""Integrity checks for golden trace bundles (EVAL-025, EVAL-026).

Beyond the bundle schema (checked by validate.py), each golden bundle and its
child bundles must be internally consistent: events valid and gap-free, UUIDv7
time prefixes matching timestamps, blobs matching their hashes and sizes and
exactly the blobs referenced, the snapshot hash per CFG-050, audit records
valid and linked, every decision audited, and children linked to their parent
calls. Messages name records by ID and never echo content.

Run from the repository root: python tools/check_golden.py
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import sys

import rfc8785
from jsonschema import Draft202012Validator

from common import ROOT, load_schemas, load_yaml, registry

AUDITED = ("hook.decision", "policy.decision", "escalation.raised")  # PORT-071


def _hash(value) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _ms(ts: str) -> int:
    return int(datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)


def _uuid_ms(u: str) -> int:
    return int(u.replace("-", "")[:12], 16)


def _blob_refs(value, out: set) -> None:
    if isinstance(value, dict):
        if {"id", "hash", "mediaType", "size"} <= value.keys() and str(value.get("hash", "")).startswith("sha256:"):
            out.add(value["id"])
        for v in value.values():
            _blob_refs(v, out)
    elif isinstance(value, list):
        for v in value:
            _blob_refs(v, out)


def check_bundle(bundle: dict, name: str, event_v, audit_v) -> list[str]:
    problems: list[str] = []

    def bad(msg: str) -> None:
        problems.append(f"{name}: {msg}")

    for i, e in enumerate(bundle.get("events", [])):
        seq = e.get("seq")
        if any(True for _ in event_v.iter_errors(e)):
            bad(f"event seq {seq} does not validate against the Event schema")
        if seq != i + 1:
            bad(f"event at index {i} has seq {seq}; sequence must be gap-free from 1")
        if _uuid_ms(e["eventId"]) != _ms(e["timestamp"]):
            bad(f"event seq {seq}: eventId time prefix does not match its timestamp")
        if e["sessionId"] != bundle["sessionId"] or e["tenantId"] != bundle["tenant"]:
            bad(f"event seq {seq}: session or tenant differs from the bundle's")
        if e["snapshotHash"] != bundle["snapshot"]["hash"]:
            bad(f"event seq {seq}: snapshotHash differs from the bundle snapshot's")

    have = {}
    for bl in bundle.get("blobs", []):
        raw = base64.b64decode(bl["base64"])
        rid = bl["ref"]["id"]
        if "sha256:" + hashlib.sha256(raw).hexdigest() != bl["ref"]["hash"]:
            bad(f"blob {rid}: hash does not match its bytes")
        if len(raw) != bl["ref"]["size"]:
            bad(f"blob {rid}: size does not match its bytes")
        have[rid] = bl
    used: set = set()
    _blob_refs(bundle.get("events", []), used)
    for rid in sorted(used - set(have)):
        bad(f"blob {rid} is referenced but missing")
    for rid in sorted(set(have) - used):
        bad(f"blob {rid} is included but never referenced")

    if _hash(bundle["snapshot"]["artifacts"]) != bundle["snapshot"]["hash"]:
        bad("snapshot hash does not match its artifacts (CFG-050)")

    events = {e["eventId"]: e for e in bundle.get("events", [])}
    for a in bundle.get("auditRecords", []):
        if any(True for _ in audit_v.iter_errors(a)):
            bad(f"audit {a['id']} does not validate against the audit record schema")
        for x in a["eventIds"]:
            if x not in events:
                bad(f"audit {a['id']} references an event not in the bundle")
        if a["type"] == "hook_decision":
            linked = [events[x] for x in a["eventIds"] if x in events]
            if linked and linked[0]["payload"] != a["details"]:
                bad(f"audit {a['id']}: details differ from its hook.decision payload (HOOK-060)")
        if a["snapshotHash"] != bundle["snapshot"]["hash"]:
            bad(f"audit {a['id']}: snapshotHash differs from the bundle snapshot's")
        if "hash" in a:
            rest = {k: v for k, v in a.items() if k != "hash"}
            if _hash(rest) != a["hash"]:
                bad(f"audit {a['id']}: hash does not match the record (PORT-073)")
    for e in bundle.get("events", []):
        if e["type"] in AUDITED and not any(e["eventId"] in a["eventIds"] for a in bundle.get("auditRecords", [])):
            bad(f"{e['type']} seq {e['seq']} has no audit record")

    calls = {e["payload"]["childSessionId"] for e in bundle.get("events", [])
             if e["type"] == "tool.call" and isinstance(e.get("payload"), dict) and e["payload"].get("childSessionId")}
    children = {c["sessionId"]: c for c in bundle.get("children", []) or []}
    for cid in sorted(set(children) - calls):
        bad(f"child bundle {cid} is not referenced by a tool.call childSessionId")
    for cid in sorted(calls - set(children)):
        bad(f"tool.call childSessionId {cid} has no child bundle")
    for cid, child in children.items():
        problems += check_bundle(child, f"{name}/child", event_v, audit_v)
    return problems


def main() -> int:
    schemas = load_schemas()
    reg = registry(schemas)
    event_v = Draft202012Validator(schemas["https://alphega.io/agentry/schemas/core/event/v1.json"], registry=reg)
    audit_v = Draft202012Validator(
        {"$ref": "https://alphega.io/agentry/schemas/ports/records/v1.json#/$defs/auditRecord"}, registry=reg)
    problems: list[str] = []
    files = sorted((ROOT / "conformance" / "golden").glob("*.yaml"))
    for f in files:
        problems += check_bundle(load_yaml(f), f.name, event_v, audit_v)
    for p in problems:
        print(f"ERROR {p}")
    print(f"{len(files)} golden bundles checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
