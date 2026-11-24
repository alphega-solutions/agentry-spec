"""Self-tests for the shared conformance runner (tools/runner, ADR-0020).

- End to end over the driver protocol, with the fake driver: the golden
  replays pass; a faulty driver fails them; fixtures the fake cannot run fail
  (never pass vacuously); the report validates and the JUnit XML parses.
- Scheduling, with a scripted in-process client: `startAfter` starts an
  action when its event is persisted, before any clock advance, and virtual
  time advances only when every in-flight action waits on a timer.

Run from the repository root: python tools/runner_test.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import xml.dom.minidom

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from jsonschema import Draft202012Validator  # noqa: E402

from common import load_schemas, registry  # noqa: E402
from runner import run as runner_run  # noqa: E402
from runner.engine import FixtureRun, Unmet  # noqa: E402

FAKE = [sys.executable, str(pathlib.Path(__file__).resolve().parent / "runner" / "fake_driver.py")]
GOLDEN = ["eval/replay-golden-*.yaml"]


def _report(globs, fault=""):
    old = os.environ.get("AGENTRY_FAKE_DRIVER_FAULT")
    os.environ["AGENTRY_FAKE_DRIVER_FAULT"] = fault
    try:
        return runner_run.run(FAKE, globs)
    finally:
        if old is None:
            os.environ.pop("AGENTRY_FAKE_DRIVER_FAULT", None)
        else:
            os.environ["AGENTRY_FAKE_DRIVER_FAULT"] = old


def test_golden_replays_pass_with_fake_driver() -> None:
    rep = _report(GOLDEN)
    assert all(r["status"] == "pass" for r in rep["results"]), [r for r in rep["results"] if r["status"] != "pass"]
    assert len(rep["results"]) >= 3
    assert not rep["conforms"], "a subset run is never a conformance claim (EVAL-023)"


def test_faulty_driver_fails() -> None:
    rep = _report(GOLDEN, fault="tool-output")
    failed = {r["fixture"]: r["firstUnmet"] for r in rep["results"] if r["status"] == "fail"}
    assert "eval.replay-golden-single-lookup" in failed, rep["results"]
    assert "events" in failed["eval.replay-golden-single-lookup"]
    assert not rep["conforms"]


def test_unsupported_fixtures_fail_not_pass() -> None:
    rep = _report(["core/session-*.yaml"])
    assert rep["results"], "expected some core session fixtures"
    assert all(r["status"] == "fail" for r in rep["results"]), "the fake driver runs no harness"


def test_report_validates_and_junit_parses() -> None:
    rep = _report(GOLDEN + ["core/session-*.yaml"])
    schemas = load_schemas()
    v = Draft202012Validator(schemas["https://alphega.io/agentry/schemas/eval/conformance-report/v1.json"],
                             registry=registry(schemas))
    errs = list(v.iter_errors(rep))
    assert not errs, errs[0].message
    xml.dom.minidom.parseString(runner_run.junit(rep))


class ScriptedClient:
    """An in-process stand-in for a driver: action A persists `x.first`, then
    waits on a timer until 10:00:05, then completes; action B (startAfter
    x.first) completes at once."""

    def __init__(self):
        self.log: list = []
        self.a_stage = 0
        self.b_started = False
        self.now = "2026-01-01T10:00:00Z"

    def call(self, method, params=None):
        self.log.append((method, params))
        if method == "action.start":
            if params["action"] == "close":
                self.b_started = True
            return {}
        if method == "clock.advance":
            self.now = params["to"]
            return {}
        if method == "settle":
            ev, done, waiting = [], [], []
            if self.a_stage == 0:
                ev.append({"process": "main", "requestId": "r1", "event": {"type": "x.first", "seq": 1}})
                self.a_stage = 1
                waiting.append({"requestId": "r1", "on": "paused"})
            elif self.a_stage == 1 and self.now < "2026-01-01T10:00:05Z":
                waiting.append({"requestId": "r1", "on": "timer", "until": "2026-01-01T10:00:05Z"})
            elif self.a_stage == 1:
                done.append({"requestId": "r1", "outcome": {"ok": True, "endReason": "responded"}})
                self.a_stage = 2
            if self.b_started and not any(o["requestId"] == "r2" for o in done):
                done.append({"requestId": "r2", "outcome": {"ok": True}})
                self.b_started = None
            return {"now": self.now, "events": ev, "completed": done, "crashed": [], "waiting": waiting}
        return {}


def test_start_after_and_clock_advance() -> None:
    client = ScriptedClient()
    fr = FixtureRun(client, {"id": "t", "script": []})
    outs = fr.run_actions([
        {"action": "run", "tenant": "t1", "expect": {"ok": True, "endReason": "responded"}},
        {"action": "close", "session": "s", "startAfter": {"type": "x.first"}, "expect": {"ok": True}},
    ], "script[0]", separate=False)
    assert outs[0]["endReason"] == "responded" and outs[1]["ok"]
    methods = [m for m, _ in client.log]
    i_close = next(i for i, (m, p) in enumerate(client.log) if m == "action.start" and p["action"] == "close")
    i_adv = methods.index("clock.advance")
    assert i_close < i_adv, "startAfter must start B before any clock advance"
    assert client.log[i_adv][1] == {"to": "2026-01-01T10:00:05Z"}, "advance to the earliest timer"
    first_settle = next(p for m, p in client.log if m == "settle")
    assert first_settle == {"pauseOnEvents": True}, "pause on events while a startAfter is pending"


def test_outcome_mismatch_is_unmet() -> None:
    client = ScriptedClient()
    fr = FixtureRun(client, {"id": "t", "script": []})
    try:
        fr.run_actions([{"action": "run", "tenant": "t1", "expect": {"ok": True, "endReason": "blocked"}},
                        {"action": "close", "session": "s", "startAfter": {"type": "x.first"}}],
                       "script[0]", separate=False)
    except Unmet as exc:
        assert "script[0][0].expect" in str(exc), str(exc)
    else:
        raise AssertionError("a wrong end reason must be unmet")


class SnapshotStoreClient:
    """A tiny, honest in-memory snapshot store behind `port.call`, for running the
    real snapshot port cases. `leak=True` ignores the tenant on `get` (a bug)."""

    def __init__(self, leak: bool = False):
        self.leak = leak
        self.store: dict = {}

    def call(self, method, params=None):
        if method == "case.begin":
            self.store = {}
            return {}
        if method != "port.call":
            return {}
        op, a = params["op"], params["args"]
        nf = {"ok": False, "error": {"code": "agentry.storage.not_found", "category": "not_found",
                                       "retryable": False, "source": "port", "message": "Not found."}}
        if op == "describe":
            return {"ok": True, "result": {"encryptedAtRest": False}}
        if op == "put":
            self.store[(a["tenant"], a["snapshot"]["hash"])] = a["snapshot"]
            return {"ok": True, "result": {}}
        if op == "get":
            key = next((k for k in self.store if k[1] == a["hash"]), None) if self.leak else (a["tenant"], a["hash"])
            return {"ok": True, "result": self.store[key]} if key in self.store else nf
        if op == "delete":
            return {"ok": True, "result": {}} if self.store.pop((a["tenant"], a["hash"]), None) else nf
        if op == "records":
            return {"ok": True, "result": [v for (t, _), v in self.store.items() if t == a["tenant"]]}
        raise AssertionError(f"unexpected op {op}")


def _snapshot_cases():
    from common import ROOT, load_yaml
    return [load_yaml(p) for p in sorted((ROOT / "conformance" / "ports").glob("snapshot-*.yaml"))]


def test_real_port_cases_pass_against_an_honest_store() -> None:
    from runner.cases import run_port_case
    cases = _snapshot_cases()
    assert len(cases) >= 5
    for doc in cases:
        run_port_case(SnapshotStoreClient(), doc, "memory")


def test_tenant_leak_fails_a_port_case() -> None:
    from runner.cases import run_port_case
    doc = next(d for d in _snapshot_cases() if d["id"].endswith("other-tenant-not-found"))
    try:
        run_port_case(SnapshotStoreClient(leak=True), doc, "memory")
    except Unmet:
        return
    raise AssertionError("a store that leaks across tenants must fail")


class ValueClient:
    def __init__(self, result):
        self.result = result

    def call(self, method, params=None):
        return self.result if method in ("cel.evaluate", "adapter.call") else {}


def test_cel_values_compare_by_type() -> None:
    from runner.cases import run_cel_case
    doc = {"id": "cel.t", "point": "beforeModelCall", "expression": "1 + 2", "expect": {"value": 3}}
    run_cel_case(ValueClient({"value": {"int": 3}}), doc)
    for wrong in ({"value": {"double": 3.0}}, {"value": {"int": 4}}, {"failure": "runtime"}):
        try:
            run_cel_case(ValueClient(wrong), doc)
        except Unmet:
            continue
        raise AssertionError(f"{wrong} must not match the int 3")
    run_cel_case(ValueClient({"failure": "compile"}),
                 {"id": "cel.f", "point": "beforeModelCall", "expression": "(", "expect": {"failure": "compile"}})
    run_cel_case(ValueClient({"value": [{"double": 1.5}, "a", None, {"k": True}]}),
                 {"id": "cel.l", "point": "beforeModelCall", "expression": "x", "expect": {"value": [1.5, "a", None, {"k": True}]}})


def test_adapter_case_with_self_provider() -> None:
    from runner.cases import run_adapter_case
    doc = {"id": "adapter.t", "condition": "ok_reasoning", "request": {"model": "m", "messages": []},
           "expect": {"parts": [{"type": "reasoning", "provider": {"$selfProvider": True}}], "usage": None}}
    run_adapter_case(ValueClient({"providerId": "vendor-x",
                                  "parts": [{"type": "reasoning", "provider": "vendor-x", "data": "r"}]}), doc, "x")
    try:
        run_adapter_case(ValueClient({"providerId": "vendor-x",
                                      "parts": [{"type": "reasoning", "provider": "other", "data": "r"}]}), doc, "x")
    except Unmet:
        return
    raise AssertionError("$selfProvider must match only the adapter's own provider")


class AbandonClient:
    """One action that persists an event per settle until its stream is abandoned."""

    def __init__(self):
        self.log: list = []
        self.n = 0
        self.abandoned_after = None

    def call(self, method, params=None):
        self.log.append((method, params))
        if method == "stream.abandon":
            self.abandoned_after = self.n
            return {}
        if method == "settle":
            if self.abandoned_after is not None:
                return {"now": "t", "events": [], "crashed": [], "waiting": [],
                        "completed": [{"requestId": "r1", "outcome": {"ok": True, "endReason": "cancelled"}}]}
            self.n += 1
            return {"now": "t", "events": [{"process": "main", "requestId": "r1", "event": {"type": f"e{self.n}"}}],
                    "completed": [], "crashed": [], "waiting": [{"requestId": "r1", "on": "paused"}]}
        return {}


def test_abandon_after_n_events() -> None:
    client = AbandonClient()
    fr = FixtureRun(client, {"id": "t", "script": []})
    fr.env["$s"] = "sess-1"
    fr.step(0, {"abandon": {"session": "$s", "afterEvents": 2}})
    fr.step(1, {"action": "run", "session": "$s", "expect": {"ok": True, "endReason": "cancelled"}})
    assert client.abandoned_after == 2, client.abandoned_after
    i_ab = next(i for i, (m, _) in enumerate(client.log) if m == "stream.abandon")
    assert all(p == {"pauseOnEvents": True} for m, p in client.log[:i_ab] if m == "settle"), \
        "pause on events until the abandon fires"


class HoldClient:
    """close() (r1) is held at after_operation_lease; decide() (r2) starts once it
    is held and fails with a retryable conflict; then close() is released and
    completes. `reach_hold=False` simulates an action that completes without
    reaching its hold point."""

    def __init__(self, reach_hold: bool = True, emit: bool = False):
        self.log: list = []
        self.reach_hold = reach_hold
        self.emit = emit  # r1 persists an event before it is held
        self.state = "start"

    def call(self, method, params=None):
        self.log.append((method, params))
        if method == "action.release":
            self.state = "released"
            return {}
        if method != "settle":
            return {}
        started = [p["requestId"] for m, p in self.log if m == "action.start"]
        done, waiting = [], []
        if not self.reach_hold:
            if self.state == "start":
                self.state = "over"
                done.append({"requestId": "r1", "outcome": {"ok": True}})
            return {"now": "t", "events": [], "completed": done, "crashed": [], "waiting": waiting}
        if self.state == "start":
            self.state = "held"
            waiting.append({"requestId": "r1", "on": "held", "point": "after_operation_lease"})
            if self.emit:
                event = {"type": "session.closed", "sessionId": "s1", "seq": 9}
                return {"now": "t", "events": [{"process": "p0", "requestId": "r1", "event": event}],
                        "completed": done, "crashed": [], "waiting": waiting}
        elif self.state == "held":
            waiting.append({"requestId": "r1", "on": "held", "point": "after_operation_lease"})
            if "r2" in started and not any(m == "decided" for m, _ in self.log):
                self.log.append(("decided", None))
                done.append({"requestId": "r2", "outcome": {"ok": False, "error": {"category": "conflict", "retryable": True}}})
        elif self.state == "released":
            self.state = "over"
            done.append({"requestId": "r1", "outcome": {"ok": True}})
        return {"now": "t", "events": [], "completed": done, "crashed": [], "waiting": waiting}


def test_hold_at_opens_a_window_for_siblings() -> None:
    client = HoldClient()
    fr = FixtureRun(client, {"id": "t", "script": []})
    fr.env["$s"] = "s1"
    outs = fr.run_actions([
        {"action": "close", "session": "$s", "holdAt": "after_operation_lease", "expect": {"ok": True}},
        {"action": "decide", "session": "$s", "decisions": [],
         "expect": {"ok": False, "error": {"category": "conflict", "retryable": True}}},
    ], "script[0]", separate=True)
    assert outs[0]["ok"] and not outs[1]["ok"]
    methods = [m for m, _ in client.log]
    starts = [p["requestId"] for m, p in client.log if m == "action.start"]
    assert starts == ["r1", "r2"]
    first_held_settle = methods.index("settle")
    assert methods.index("action.start", first_held_settle) > first_held_settle, "decide starts only once close is held"
    assert methods.index("action.release") > methods.index("decided"), "release only after the sibling completed"
    assert client.log[0][1].get("holdAt") == "after_operation_lease"


def test_events_while_siblings_wait_for_a_hold() -> None:
    """A sibling held back by `holdAt` has no `startAfter`; an event persisted
    meanwhile must not be matched against one."""
    client = HoldClient(emit=True)
    fr = FixtureRun(client, {"id": "t", "script": []})
    fr.env["$s"] = "s1"
    outs = fr.run_actions([
        {"action": "close", "session": "$s", "holdAt": "after_operation_lease", "expect": {"ok": True}},
        {"action": "decide", "session": "$s", "decisions": []},
    ], "script[0]", separate=True)
    assert outs[0]["ok"] and not outs[1]["ok"]


def test_hold_point_never_reached_is_unmet() -> None:
    fr = FixtureRun(HoldClient(reach_hold=False), {"id": "t", "script": []})
    fr.env["$s"] = "s1"
    try:
        fr.run_actions([{"action": "close", "session": "$s", "holdAt": "after_operation_lease"},
                        {"action": "decide", "session": "$s", "decisions": []}], "script[0]", separate=True)
    except Unmet as exc:
        assert "without reaching holdAt" in str(exc), str(exc)
    else:
        raise AssertionError("an action that never reaches its hold point must be unmet")


class ObserveClient:
    def call(self, method, params=None):
        return {"delivered": {}} if method == "observe" else {}


def test_no_returned_content() -> None:
    fr = FixtureRun(ObserveClient(), {"id": "t", "script": []})
    fr.outcomes = [{"ok": True, "view": {"actions": [{"arguments": {"note": "SYN-SECRET-0001"}}]}}]
    try:
        fr.check_expect({"noReturnedContent": ["SYN-SECRET-0001"]})
    except Unmet as exc:
        assert "returned to the host" in str(exc)
    else:
        raise AssertionError("a secret in a returned view must be unmet")
    fr.check_expect({"noReturnedContent": ["SYN-OTHER"]})


def main() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
