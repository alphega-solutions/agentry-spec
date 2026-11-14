"""Tests for the reference expectation matcher (tools/matcher.py, EVAL-004).

Hand-built cases pin each rule in conformance/README.md; a corpus check runs
the replay fixtures' event patterns against the golden bundles they replay.

Run from the repository root: python tools/matcher_test.py
"""
from __future__ import annotations

import sys

from common import ROOT, load_yaml
from matcher import Matcher, UnboundPlaceholder

M = Matcher()


def ev(type_: str, **payload) -> dict:
    return {"type": type_, "payload": payload}


def test_partial_objects_and_exact_arrays() -> None:
    actual = {"a": 1, "b": {"c": 2, "d": 3}, "xs": [1, 2]}
    assert M.matches({"b": {"c": 2}}, actual)
    assert not M.matches({"b": {"c": 9}}, actual)
    assert not M.matches({"xs": [1]}, actual), "arrays written out must have the same length"
    assert M.matches({"xs": [1, 2]}, actual)
    assert not M.matches({"missing": 1}, actual)


def test_json_equality() -> None:
    assert M.matches({"n": 1}, {"n": 1.0})
    assert not M.matches({"n": True}, {"n": 1})
    assert not M.matches({"n": 1}, {"n": True})


def test_scalar_matchers() -> None:
    a = {"s": "agentry.tool.timeout", "n": 5, "xs": [1, 2, 3]}
    assert M.matches({"s": {"$regex": "^agentry\\.tool\\."}}, a)
    assert M.matches({"n": {"$gte": 5, "$lte": 5}}, a)
    assert not M.matches({"n": {"$gte": 6}}, a)
    assert M.matches({"xs": {"$len": 3}}, a)
    assert M.matches({"xs": {"$every": {"$gte": 1}}}, a)
    assert M.matches({"s": {"$any": True}}, a)
    assert not M.matches({"zz": {"$any": True}}, a)
    assert M.matches({"zz": {"$absent": True}}, a)
    assert not M.matches({"s": {"$absent": True}}, a)
    assert M.matches({"xs": {"$count": {"of": {"$gte": 2}, "equals": 2}}}, a)
    assert M.matches({"xs": {"$all": [{"$len": 3}, {"$contains": [3, 1]}]}}, a)


def test_not_matches_absent_and_never_binds() -> None:
    assert M.matches({"x": {"$not": 1}}, {}), "$not matches an absent field"
    assert M.matches({"x": {"$not": 1}}, {"x": 2})
    assert not M.matches({"x": {"$not": 1}}, {"x": 1})
    try:
        M.matches({"x": {"$not": "$unbound"}}, {"x": 1})
    except UnboundPlaceholder:
        pass
    else:
        raise AssertionError("an unbound placeholder under $not must be an error")
    assert M.matches({"a": "$p", "x": {"$not": "$p"}}, {"a": 1, "x": 2})
    assert not M.matches({"a": "$p", "x": {"$not": "$p"}}, {"a": 1, "x": 1})


def test_placeholders_bind_once_and_compare_deeply() -> None:
    env = M.first({"a": "$p", "b": "$p"}, {"a": {"k": [1]}, "b": {"k": [1]}})
    assert env == {"$p": {"k": [1]}}, env
    assert not M.matches({"a": "$p", "b": "$p"}, {"a": {"k": [1]}, "b": {"k": [1], "extra": 0}}), \
        "a bound placeholder needs deep equality, not partial matching"


def test_placeholder_keys() -> None:
    store = {"k-1": {"state": "started"}, "k-2": {"state": "completed"}}
    env = M.first({"$k": {"state": "completed"}}, store)
    assert env == {"$k": "k-2"}, env
    assert M.matches({"$k": {"$absent": True}}, store, {"$k": "k-9"})
    assert not M.matches({"$k": {"$absent": True}}, store, {"$k": "k-1"})
    try:
        M.matches({"$k": {"$absent": True}}, store)
    except UnboundPlaceholder:
        pass
    else:
        raise AssertionError("$absent under an unbound key placeholder must be an error")


def test_contains_searches_not_greedy() -> None:
    """The README example: a generic item listed before a specific one."""
    results = [{"type": "tool_result", "callId": "c1"}, {"type": "tool_result", "callId": "c2"}]
    pattern = {"$contains": [{"type": "tool_result"}, {"type": "tool_result", "callId": "c1"}]}
    assert M.matches(pattern, results), "a greedy matcher fails here; a search succeeds"
    assert not M.matches({"$contains": [{"callId": "c1"}, {"callId": "c1"}]}, results), "elements are distinct"


def test_canonical_binding() -> None:
    """Items in listed order, each given the earliest element that still lets
    the rest match: $x cannot take c1 (the second item needs it), so $x = c2."""
    results = [{"callId": "c1"}, {"callId": "c2"}]
    env = M.first({"$contains": [{"callId": "$x"}, {"callId": "c1"}]}, results)
    assert env == {"$x": "c2"}, env
    env = M.first({"$contains": [{"callId": "$x"}, {"callId": "$y"}]}, results)
    assert env == {"$x": "c1", "$y": "c2"}, env


def test_event_modes() -> None:
    log = [ev("session.created"), ev("run.started"), ev("checkpoint.saved"),
           ev("tool.call", callId="c2"), ev("tool.call", callId="c1"), ev("run.ended")]
    seq = {"mode": "sequence", "items": [{"type": t} for t in
                                         ("session.created", "run.started", "tool.call", "tool.call", "run.ended")]}
    assert M.events(seq, log) is not None, "checkpoint.saved is ignored unless named"
    named = dict(seq, items=seq["items"][:2] + [{"type": "checkpoint.saved"}] + seq["items"][2:])
    assert M.events(named, log) is not None
    unordered = {"mode": "unordered", "items": [{"type": "run.ended"}, {"type": "tool.call", "payload": {"callId": "c1"}},
                                                 {"type": "tool.call"}, {"type": "run.started"},
                                                 {"type": "session.created"}]}
    assert M.events(unordered, log) is not None, "a greedy unordered match would give c1 to the generic item"
    assert M.events({"mode": "contains", "items": [{"type": "run.ended"}, {"type": "session.created"}]}, log) is not None
    assert M.events({"mode": "subsequence", "items": [{"type": "run.ended"}, {"type": "session.created"}]}, log) is None
    assert M.events({"mode": "sequence", "items": seq["items"][:-1]}, log) is None, "sequence needs every event"


def test_subsequence_with_placeholder_backtracks() -> None:
    """Binding $p on the earliest `a` makes the `b` item fail; a later `a` works."""
    log = [ev("a", v=1), ev("a", v=2), ev("b", v=2)]
    pattern = {"mode": "subsequence", "items": [{"type": "a", "payload": {"v": "$p"}},
                                               {"type": "b", "payload": {"v": "$p"}}]}
    env = M.events(pattern, log)
    assert env == {"$p": 2}, env


def test_absent_events() -> None:
    log = [ev("tool.call", callId="c1"), ev("run.ended")]
    assert M.absent_events([{"type": "escalation.raised"}], log, {}) == []
    assert M.absent_events([{"type": "tool.call", "payload": {"callId": "$c"}}], log, {"$c": "c1"})
    try:
        M.absent_events([{"type": "tool.call", "payload": {"callId": "$c"}}], log, {})
    except UnboundPlaceholder:
        pass
    else:
        raise AssertionError("absentEvents must not bind placeholders")


def _without_absent(value):
    if isinstance(value, dict):
        return {k: _without_absent(v) for k, v in value.items()
                if not (isinstance(v, dict) and set(v) == {"$absent"})}
    if isinstance(value, list):
        return [_without_absent(v) for v in value]
    return value


def test_golden_replays_match_their_bundles() -> None:
    """Each replay fixture's pattern for the replayed session should match the
    golden bundle it replays, except for what differs by design between a
    recording and its replay (session ID, and items the fixture marks as
    replay-only); checked here on the event types and payloads only."""
    checked = 0
    for fx in sorted((ROOT / "conformance" / "eval").glob("replay-golden-*.yaml")):
        doc = load_yaml(fx)
        bundle_path = next(s["bundle"] for s in doc["script"] if s.get("action") == "replay")
        bundle = load_yaml(ROOT / "conformance" / bundle_path)
        for name, sess in (doc.get("expect") or {}).get("sessions", {}).items():
            pattern = sess.get("events")
            if not pattern:
                continue
            # Compare on type and payload: IDs, runs and timestamps of a replay
            # are new by design. `$absent` assertions mark what a replay omits
            # by design (e.g. an agent call answered from the recording has no
            # childSessionId, Area 11 reading of EVAL-060/062), so drop them.
            items = [_without_absent({k: v for k, v in it.items() if k in ("type", "payload")})
                     for it in pattern["items"]]
            env = M.events({**pattern, "items": items}, bundle["events"])
            assert env is not None, f"{fx.name}: {name}'s events do not match {bundle_path}"
            checked += 1
    assert checked >= 3, f"expected several replay fixtures, checked {checked}"


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
