"""Port cases, provider adapter cases and CEL rule fixtures (ADR-0020).

Each runs through the driver with fresh state (`case.begin`) and is judged by
the runner with the reference matcher.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from common import load_schemas, registry
from matcher import Matcher, UnboundPlaceholder, is_placeholder

from runner.engine import Unmet

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")

# Port → the schema each stored record must validate against (PORT-007, `storedRecords`).
RECORD_SCHEMAS = {
    "eventLog": "https://alphega.io/agentry/schemas/core/event/v1.json",
    "checkpointStore": "https://alphega.io/agentry/schemas/ports/records/v1.json#/$defs/checkpoint",
    "idempotencyStore": "https://alphega.io/agentry/schemas/ports/records/v1.json#/$defs/idempotencyRecord",
    "snapshotStore": "https://alphega.io/agentry/schemas/ports/records/v1.json#/$defs/snapshotRecord",
    "blobStore": "https://alphega.io/agentry/schemas/ports/records/v1.json#/$defs/blobRecord",
    "auditLog": "https://alphega.io/agentry/schemas/ports/records/v1.json#/$defs/auditRecord",
}


def add_duration(ts: str, duration: str) -> str:
    """Add an ISO 8601 duration of days, hours, minutes and seconds to a UTC timestamp."""
    m = _DURATION.match(duration)
    if not m or not any(m.groups()):
        raise Unmet(f"unsupported duration {duration!r}")
    d, h, mi, s = m.groups()
    delta = dt.timedelta(days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=float(s or 0))
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) + delta
    return t.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sub(value: Any, env: dict, where: str) -> Any:
    if is_placeholder(value):
        if value not in env:
            raise Unmet(f"{where}: {value} is not bound")
        return env[value]
    if isinstance(value, dict):
        return {(_sub(k, env, where) if is_placeholder(k) else k): _sub(v, env, where) for k, v in value.items()}
    if isinstance(value, list):
        return [_sub(v, env, where) for v in value]
    return value


def _path(value: Any, path: str, where: str) -> Any:
    if path == "":
        return value
    for part in path.split("."):
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise Unmet(f"{where}: the result has no `{path}`")
    return value


def _match(m: Matcher, exp: Any, actual: Any, env: dict, where: str) -> None:
    try:
        got = m.first(exp, actual, env)
    except UnboundPlaceholder as exc:
        raise Unmet(f"{where}: {exc}") from exc
    if got is None:
        raise Unmet(f"{where}: expected {json.dumps(exp, default=str)[:300]}, got {json.dumps(actual, default=str)[:300]}")
    env.update(got)


def run_port_case(client, doc: dict, adapter: str) -> None:
    port, m = doc["port"], Matcher()
    now = doc.get("clock", "2026-01-01T00:00:00Z")
    client.call("case.begin", {"caseId": doc["id"], "kind": "port", **({"clock": doc["clock"]} if "clock" in doc else {})})
    env: dict = {}
    tenants: set[str] = set()
    for i, st in enumerate(doc.get("steps") or []):
        where = f"steps[{i}]"
        if "clock" in st:
            now = add_duration(now, st["clock"]["advance"])
            client.call("clock.advance", {"by": st["clock"]["advance"]})
            continue
        args = _sub(st.get("args") or {}, {**env, "$now": now}, where)
        if isinstance(args.get("tenant"), str):
            tenants.add(args["tenant"])
        res = client.call("port.call", {"port": port, "adapter": adapter, "op": st["op"], "args": args})
        exp = st.get("expect") or {}
        ok = bool(res.get("ok"))
        want_ok = exp.get("ok", "error" not in exp)
        if ok != want_ok:
            detail = res.get("error") if not ok else res.get("result")
            raise Unmet(f"{where} {st['op']}: expected ok={want_ok}, got ok={ok} ({json.dumps(detail, default=str)[:200]})")
        if "error" in exp:
            _match(m, exp["error"], res.get("error") or {}, env, f"{where}.expect.error")
        if "result" in exp:
            _match(m, exp["result"], res.get("result"), env, f"{where}.expect.result")
        for path, ph in (st.get("bind") or {}).items():
            env[ph] = _path(res.get("result"), path, f"{where}.bind")
    if doc.get("storedRecords", True) and port in RECORD_SCHEMAS:
        check_stored_records(client, port, adapter, sorted(tenants))


def check_stored_records(client, port: str, adapter: str, tenants: list[str]) -> None:
    from jsonschema import Draft202012Validator, FormatChecker
    schemas = load_schemas()
    wrapper = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": RECORD_SCHEMAS[port]}
    v = Draft202012Validator(wrapper, registry=registry(schemas), format_checker=FormatChecker())
    for tenant in tenants:
        res = client.call("port.call", {"port": port, "adapter": adapter, "op": "records", "args": {"tenant": tenant}})
        if not res.get("ok"):
            raise Unmet(f"storedRecords: `records` failed for tenant {tenant}")
        for rec in res.get("result") or []:
            if "schemaVersion" not in rec:
                raise Unmet(f"storedRecords: a {port} record has no schemaVersion (PORT-007)")
            err = next(iter(v.iter_errors(rec)), None)
            if err is not None:
                raise Unmet(f"storedRecords: a {port} record is invalid: {err.message[:200]}")


def run_adapter_case(client, doc: dict, adapter: str) -> None:
    client.call("case.begin", {"caseId": doc["id"], "kind": "adapter"})
    res = client.call("adapter.call", {"adapter": adapter, "case": doc})
    m, env = Matcher(self_provider=res.get("providerId")), {}
    exp = doc.get("expect") or {}
    for key in ("parts", "usage", "error", "wire"):
        if key in exp:
            if key == "usage" and exp[key] is None:
                if res.get("usage") is not None:
                    raise Unmet("expect.usage: the provider reported none, so the adapter must report none")
                continue
            _match(m, exp[key], res.get(key), env, f"expect.{key}")
    if "error" not in exp and res.get("error"):
        raise Unmet(f"expect: the adapter returned an error {json.dumps(res['error'])[:200]}")


def typed(value: Any) -> Any:
    """A YAML value in the CEL typed encoding (driver.yaml `celResult`)."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return {"int": value}
    if isinstance(value, float):
        return {"double": value}
    if isinstance(value, list):
        return [typed(v) for v in value]
    if isinstance(value, dict):
        return {k: typed(v) for k, v in value.items()}
    raise Unmet(f"unsupported expected value {value!r}")


def _typed_equal(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() == b.keys() and len(a) == 1 and next(iter(a)) in ("int", "uint", "double"):
            return a == b  # same CEL numeric type and value
        return a.keys() == b.keys() and all(_typed_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_typed_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def run_cel_case(client, doc: dict) -> None:
    client.call("case.begin", {"caseId": doc["id"], "kind": "cel"})
    res = client.call("cel.evaluate", {"point": doc["point"], "expression": doc["expression"],
                                       "variables": doc.get("variables") or {}})
    exp = doc["expect"]
    if "failure" in exp:
        if res.get("failure") != exp["failure"]:
            raise Unmet(f"expect.failure: expected {exp['failure']}, got {json.dumps(res)[:200]}")
        return
    if "failure" in res:
        raise Unmet(f"expect.value: evaluation failed at {res['failure']}")
    if not _typed_equal(typed(exp["value"]), res.get("value")):
        raise Unmet(f"expect.value: expected {json.dumps(typed(exp['value']))}, got {json.dumps(res.get('value'))}")
