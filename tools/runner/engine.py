"""Executes one fixture against a driver and judges it (ADR-0020, EVAL-020).

The runner owns every interpretation: configuration resolution, placeholder
substitution, `startAfter`, captures, scheduling (when virtual time
advances) and all expectations. The driver only executes and reports.
"""
from __future__ import annotations

import base64
import copy
import json
from typing import Any

import validate
from common import ROOT, load_schemas, load_yaml, registry
from matcher import Matcher, UnboundPlaceholder, is_placeholder

from runner.client import DriverClient, DriverError

MAX_SETTLES = 10_000


class Unmet(Exception):
    """An expectation was not met; the message is the report's `firstUnmet`."""


class NotSupported(Unmet):
    """The runner does not yet execute this part of the fixture format."""


class FixtureRun:
    def __init__(self, client: DriverClient, doc: dict):
        self.c, self.doc = client, doc
        self.m = Matcher()
        self.env: dict[str, Any] = {}
        self.artifacts: dict = {}
        self.overlay: dict | None = None
        self.outcomes: list[dict | None] = []
        self.events_by_request: dict[str, list[dict]] = {}
        self.armed_crash = False
        self._rid = 0

    # ---- entry point ----------------------------------------------------------

    def execute(self) -> None:
        setup = copy.deepcopy(self.doc.get("setup") or {})
        cfg = setup.get("config") or {}
        base = validate._base_artifacts(cfg["base"]) if cfg.get("base") else {}
        self.artifacts = validate._apply(base or {}, cfg.get("artifacts"), cfg.get("remove"))
        self.overlay = cfg.get("overlay")
        setup["config"] = {"artifacts": list(self.artifacts.values()),
                           **({"overlay": self.overlay} if self.overlay else {})}
        self.c.call("fixture.begin", {"fixtureId": self.doc["id"], "setup": setup})
        try:
            for i, step in enumerate(self.doc.get("script") or []):
                self.step(i, step)
            self.check_expect(self.doc.get("expect") or {})
        finally:
            try:
                self.c.call("fixture.end", {})
            except DriverError:
                pass

    # ---- steps ------------------------------------------------------------------

    def step(self, i: int, step: dict) -> None:
        where = f"script[{i}]"
        if "action" in step:
            self.outcomes.append(self.run_actions([step], where, separate=False)[0])
        elif "load" in step:
            self.outcomes.append(self.load(step, where))
        elif "concurrently" in step:
            subs = step["concurrently"] or []
            outs = self.run_actions(subs, where, separate=bool(step.get("separateProcesses")))
            exp = (step.get("expect") or {}).get("outcomes")
            if exp is not None:
                self.match_outcome_multiset(exp, outs, where)
            self.outcomes.append(None)
        elif "clock" in step:
            clk = step["clock"]
            if "set" in clk:
                self.c.call("clock.set", {"to": clk["set"]})
            else:
                self.c.call("clock.advance", {"by": clk["advance"]})
            self.outcomes.append(None)
        elif "crash" in step:
            crash = step["crash"] or {}
            params = {"point": crash["at"], "process": "main"}
            if crash.get("session"):
                params["session"] = self.sub(crash["session"], where)
            self.c.call("crash.arm", params)
            self.armed_crash = True
            self.outcomes.append(None)
        elif "restart" in step:
            self.c.call("process.restart", {"process": "main"})
            self.outcomes.append(None)
        elif "retention" in step:
            self.c.call("retention.run", {})
            self.outcomes.append(None)
        else:
            raise NotSupported(f"{where}: step kind {sorted(step)} is not executed by this runner yet")

    def load(self, step: dict, where: str) -> dict:
        ld = step["load"] or {}
        arts = validate._apply(self.artifacts, validate._load_artifacts({"artifacts": ld.get("artifacts")}),
                               ld.get("remove"))
        params: dict = {"artifacts": list(arts.values())}
        if ld.get("raw"):
            params["raw"] = list(ld["raw"])
        overlay = ld.get("overlay", self.overlay)
        if overlay:
            params["overlay"] = overlay
        res = self.c.call("config.load", params)
        if res.get("ok"):
            self.artifacts, self.overlay = arts, overlay
            if isinstance(step.get("bind"), str):
                self.env[step["bind"]] = res.get("snapshotHash")
        if "expect" in step:
            self.match_outcome(step["expect"], res, f"{where}.expect")
        return res

    def run_actions(self, steps: list[dict], where: str, separate: bool) -> list[dict | None]:
        """Start the actions in listed order, each after the previous has begun,
        honouring `startAfter`, and drive them all to completion."""
        rids: list[str] = []
        crashed_any = False
        waiting: list[tuple[int, dict]] = []
        started: dict[str, int] = {}
        outcomes: dict[str, dict | None] = {}

        def start(k: int, st: dict) -> None:
            self._rid += 1
            rid = f"r{self._rid}"
            args = {key: self.sub(v, f"{where}[{k}]") for key, v in st.items()
                    if key not in ("action", "bind", "bindResult", "capture", "expect", "startAfter")}
            if isinstance(args.get("bundle"), str):
                args["bundle"] = load_yaml(ROOT / "conformance" / args["bundle"])
            process = f"p{k}" if separate else "main"
            self.c.call("action.start", {"requestId": rid, "process": process, "action": st["action"], "args": args})
            rids.append(rid)
            started[rid] = k
            self.events_by_request[rid] = []

        for k, st in enumerate(steps):
            if "startAfter" in st and k > 0:
                waiting.append((k, st))
            else:
                start(k, st)

        for _ in range(MAX_SETTLES):
            res = self.c.call("settle", {"pauseOnEvents": bool(waiting)})
            for ev in res.get("events") or []:
                rid = ev.get("requestId")
                if rid in self.events_by_request:
                    self.events_by_request[rid].append(ev["event"])
                for w in list(waiting):  # startAfter: evaluated before any clock advance
                    try:
                        hit = self.m.matches(w[1]["startAfter"], ev["event"], self.env)
                    except UnboundPlaceholder as exc:
                        raise Unmet(f"{where}[{w[0]}].startAfter: {exc}") from exc
                    if hit:
                        waiting.remove(w)
                        start(*w)
            for c in res.get("completed") or []:
                outcomes[c["requestId"]] = c["outcome"]
            for c in res.get("crashed") or []:
                outcomes[c["requestId"]] = None
                crashed_any = True
            if all(r in outcomes for r in rids) and not waiting:
                break
            pending = res.get("waiting") or []
            if pending and all(w.get("on") == "timer" for w in pending) and not res.get("events") \
                    and not res.get("completed"):
                self.c.call("clock.advance", {"to": min(w["until"] for w in pending)})
            elif not pending and not res.get("events") and not res.get("completed"):
                missing = [started[r] for r in rids if r not in outcomes] + [k for k, _ in waiting]
                raise Unmet(f"{where}: actions {missing} never completed (and no startAfter event was persisted)")
        else:
            raise Unmet(f"{where}: actions did not settle within {MAX_SETTLES} rounds")

        results: list[dict | None] = [None] * len(steps)
        for rid in rids:
            k, st, out = started[rid], steps[started[rid]], outcomes.get(rid)
            results[k] = out
            if out is None:  # crashed: no outcome, `expect` not checked
                continue
            if isinstance(st.get("bind"), str) and out.get("sessionId"):
                self.env.setdefault(st["bind"], out["sessionId"])
            if isinstance(st.get("bindResult"), str):
                self.env[st["bindResult"]] = out.get("bundle") or out.get("report") or out
            for j, cap in enumerate(st.get("capture") or []):
                self.capture(cap, self.events_by_request[rid], f"{where}[{k}].capture[{j}]")
            if "expect" in st and not (self.armed_crash and crashed_any):
                self.match_outcome(st["expect"], out, f"{where}[{k}].expect", rid)
        if crashed_any:
            self.armed_crash = False
        return results

    def capture(self, cap: dict, events: list[dict], where: str) -> None:
        pattern = cap.get("event") or {}
        for e in events:
            env = self.m.first(pattern, e, self.env)
            if env is None:
                continue
            self.env.update(env)
            for path, ph in (cap.get("bind") or {}).items():
                value: Any = e
                for part in str(path).split("."):
                    if isinstance(value, list) and part.isdigit() and int(part) < len(value):
                        value = value[int(part)]
                    elif isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        raise Unmet(f"{where}: captured event has no `{path}`")
                if ph in self.env and self.env[ph] != value:
                    raise Unmet(f"{where}: {ph} is already bound to a different value")
                self.env[ph] = value
            return
        raise Unmet(f"{where}: no event of the action matched {json.dumps(pattern)}")

    # ---- outcomes ----------------------------------------------------------------

    def match_outcome(self, exp: dict, out: dict | None, where: str, rid: str | None = None) -> None:
        if not self.outcome_matches(exp, out, rid):
            raise Unmet(f"{where}: expected {json.dumps(exp, default=str)}, got {json.dumps(out, default=str)[:400]}")

    def outcome_matches(self, exp: dict, out: dict | None, rid: str | None = None) -> bool:
        if out is None:
            return False
        exp = dict(exp)
        if "sameAs" in exp:
            other = self.outcomes[exp.pop("sameAs")]
            if other is None or {k: v for k, v in other.items() if k != "newEvents"} != \
                    {k: v for k, v in out.items() if k != "newEvents"}:
                return False
        if "newEvents" in exp:
            n = exp.pop("newEvents")
            got = out.get("newEvents", len(self.events_by_request.get(rid or "", [])))
            if got != n:
                return False
        env = self.m.first(exp, out, self.env)
        if env is None:
            return False
        self.env.update(env)
        return True

    def match_outcome_multiset(self, exp: list[dict], outs: list[dict | None], where: str) -> None:
        def assign(i: int, used: set) -> bool:
            if i == len(exp):
                return True
            return any(j not in used and self.outcome_matches(exp[i], outs[j]) and assign(i + 1, used | {j})
                       for j in range(len(outs)))
        if len(exp) != len(outs) or not assign(0, set()):
            raise Unmet(f"{where}.expect.outcomes: no assignment of {json.dumps(exp)} to {json.dumps(outs, default=str)[:400]}")

    # ---- expectations --------------------------------------------------------------

    def check_expect(self, expect: dict) -> None:
        obs = self.c.call("observe", {"items": ["ports", "stubCalls", "providerRequests", "delivered", "telemetrySpans"]})
        ports = obs.get("ports") or {}
        for key, exp in expect.items():  # document order
            where = f"expect.{key}"
            if key == "sessions":
                for skey, sexp in exp.items():
                    self.check_session(skey, sexp, ports, f"{where}.{skey}")
            elif key in ("stubCalls", "providerRequests"):
                actual = obs.get(key) or {}
                for k, e in exp.items():
                    got = actual.get(k, [])
                    if isinstance(e, dict) and set(e) == {"count"}:
                        if len(got) != e["count"]:
                            raise Unmet(f"{where}.{k}: expected {e['count']} records, got {len(got)}")
                    else:
                        self.match(e, got, f"{where}.{k}")
            elif key == "ports":
                self.match(exp, ports, where)
            elif key == "delivered":
                self.match(exp, obs.get("delivered") or {}, where)
            elif key == "noPersistedContent":
                for item in exp:
                    names = item["ports"] if isinstance(item, dict) else list(ports)
                    strings = item["strings"] if isinstance(item, dict) else [item]
                    text = _searchable({n: ports.get(n) for n in names})
                    for s in strings:
                        if s in text:
                            raise Unmet(f"{where}: {s!r} is persisted")
            elif key == "noTransmittedContent":
                text = _searchable([obs.get("stubCalls"), obs.get("providerRequests")])
                for s in exp:
                    if s in text:
                        raise Unmet(f"{where}: {s!r} was transmitted")
            elif key == "noTelemetryContent":
                text = _searchable(obs.get("telemetrySpans"))
                for s in exp:
                    if s in text:
                        raise Unmet(f"{where}: {s!r} was exported")
            elif key == "telemetrySpanCount":
                self.match(exp, len(obs.get("telemetrySpans") or []), where)
            elif key == "schemaValid":
                if exp:
                    self.check_events_valid(ports, where)
            else:
                raise NotSupported(f"{where}: not evaluated by this runner yet")

    def check_session(self, skey: str, sexp: dict, ports: dict, where: str) -> None:
        sid = self.env.get(skey) if is_placeholder(skey) else skey
        if sid is None:
            raise Unmet(f"{where}: {skey} is not bound")
        events = next((t[sid] for t in (ports.get("eventLog") or {}).values() if sid in t), None)
        cp = next((t[sid] for t in (ports.get("checkpointStore") or {}).values() if sid in t), None)
        for k, e in sexp.items():
            if k in ("state", "closeReason"):
                got = (cp or {}).get(k)
                if got != e:
                    raise Unmet(f"{where}.{k}: expected {e!r}, got {got!r}")
            elif k == "checkpoint":
                self.match(e, cp, f"{where}.checkpoint")
            elif k == "events":
                if events is None:
                    raise Unmet(f"{where}.events: the session has no events")
                env = self.m.events(e, events, self.env)
                if env is None:
                    raise Unmet(f"{where}.events: no {e.get('mode')} match for the {len(e.get('items') or [])} items")
                self.env.update(env)
            elif k == "absentEvents":
                try:
                    hits = self.m.absent_events(e, events or [], self.env)
                except UnboundPlaceholder as exc:
                    raise Unmet(f"{where}.absentEvents: {exc}") from exc
                if hits:
                    raise Unmet(f"{where}.absentEvents: an event matched {json.dumps(hits[0])}")
            elif k == "eventCount":
                if len(events or []) != e:
                    raise Unmet(f"{where}.eventCount: expected {e}, got {len(events or [])}")
            else:
                raise NotSupported(f"{where}.{k}: not evaluated by this runner yet")

    def check_events_valid(self, ports: dict, where: str) -> None:
        from jsonschema import Draft202012Validator, FormatChecker
        schemas = load_schemas()
        v = Draft202012Validator(schemas["https://alphega.io/agentry/schemas/core/event/v1.json"],
                                 registry=registry(schemas), format_checker=FormatChecker())
        for t in (ports.get("eventLog") or {}).values():
            for evs in t.values():
                for e in evs:
                    err = next(iter(v.iter_errors(e)), None)
                    if err is not None:
                        raise Unmet(f"{where}: event seq {e.get('seq')} is invalid: {err.message[:200]}")

    def match(self, exp: Any, actual: Any, where: str) -> None:
        try:
            env = self.m.first(exp, actual, self.env)
        except UnboundPlaceholder as exc:
            raise Unmet(f"{where}: {exc}") from exc
        if env is None:
            raise Unmet(f"{where}: expected {json.dumps(exp, default=str)[:300]}, got {json.dumps(actual, default=str)[:300]}")
        self.env.update(env)

    # ---- placeholders --------------------------------------------------------------

    def sub(self, value: Any, where: str) -> Any:
        """Substitute bound placeholders in a step's arguments."""
        if is_placeholder(value):
            if value not in self.env:
                raise Unmet(f"{where}: {value} is not bound")
            return self.env[value]
        if isinstance(value, dict):
            return {self.sub(k, where) if is_placeholder(k) else k: self.sub(v, where) for k, v in value.items()}
        if isinstance(value, list):
            return [self.sub(v, where) for v in value]
        return value


def _searchable(value: Any) -> str:
    """All strings in `value`, with blob `data` (base64) decoded too."""
    parts: list[str] = []

    def walk(v: Any, key: str = "") -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str):
            parts.append(v)
            if key == "data":
                try:
                    parts.append(base64.b64decode(v, validate=True).decode("utf-8", "replace"))
                except Exception:  # noqa: BLE001 - not base64
                    pass
    walk(value)
    return "\n".join(parts)
