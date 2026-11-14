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
