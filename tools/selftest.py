"""Spec-CI self-tests: the checks EVAL-002, EVAL-010 and EVAL-024 require of the
validator and the coverage tool, and the validator's bespoke checks, are exercised
on deliberately broken inputs (each also confirms a correct input passes where
that is cheap).

Run from the repository root: python tools/selftest.py
"""
from __future__ import annotations

import contextlib
import copy
import io
import sys

import coverage as coverage_tool
import validate
from common import fixture_files, load_yaml, spec_requirements


def test_unbound_placeholder_rejected() -> None:
    """EVAL-002: a placeholder used in a step before any capture binds it is an error."""
    doc = {
        "script": [
            {"action": "run", "bind": "$s", "tenant": "t1", "principal": "p1", "persona": "assistant@1",
             "input": [{"type": "text", "text": "Hi"}]},
            {"action": "run", "session": "$neverBound", "principal": "p1",
             "input": [{"type": "text", "text": "Again"}]},
        ],
        "expect": {},
    }
    problems = validate.check_placeholders(doc)
    assert any("$neverBound" in p for p in problems), problems


def test_coverage_fails_when_last_fixture_removed() -> None:
    """EVAL-010: coverage fails when a normative requirement loses its last fixture."""
    reqs = spec_requirements()
    target = "CORE-001"
    assert reqs[target]["normative"]
    docs = [load_yaml(f) for f in fixture_files()]
    stripped = []
    for d in docs:
        d = copy.deepcopy(d)
        if target in (d.get("requirements") or []):
            d["requirements"] = [r for r in d["requirements"] if r != target] or ["CORE-002"]
        stripped.append(d)
    original = coverage_tool.fixture_docs
    coverage_tool.fixture_docs = lambda: stripped
    quiet = contextlib.redirect_stdout(io.StringIO())
    try:
        with quiet:
            assert coverage_tool.main() == 1, "coverage passed although CORE-001 has no fixture"
    finally:
        coverage_tool.fixture_docs = original
    with contextlib.redirect_stdout(io.StringIO()):
        assert coverage_tool.main() == 0, "coverage fails on the unmodified suite"


def test_real_endpoint_rejected() -> None:
    """EVAL-024: a fixture URL outside the reserved test domains is an error; test domains and in-process schemes are not."""
    assert validate.check_offline({"stubs": {"http": [{"url": "https://api.real-vendor.com/v1"}]}})
    assert not validate.check_offline({"stubs": {"http": [{"url": "https://files.example.test/a"}]},
                                       "providers": [{"endpoint": "memory://scripted-a"}]})


# --- Negative tests for the bespoke validator checks -------------------------

_RUN = {"action": "run", "tenant": "t1", "principal": "p1", "persona": "assistant@1",
        "input": [{"type": "text", "text": "Hi"}]}


def _example_validator(target: str):
    from jsonschema import Draft202012Validator, FormatChecker
    from common import load_schemas, registry
    schemas = load_schemas()
    wrapper = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": target}
    return Draft202012Validator(wrapper, registry=registry(schemas), format_checker=FormatChecker())


def test_invalid_example_needs_a_working_repair() -> None:
    """An invalid schema example must declare `repair`, and the repaired instance must
    validate, so the example fails only for the fault it documents."""
    from common import ROOT
    doc = load_yaml(ROOT / "schemas/config/v1/examples/invalid/persona-approval-default.yaml")
    v = _example_validator(doc["schema"])
    assert not validate.check_repair(doc, v), "the real example's repair should hold"
    missing = {k: x for k, x in doc.items() if k != "repair"}
    assert validate.check_repair(missing, v), "an invalid example without `repair` passed"
    second_fault = copy.deepcopy(doc)
    second_fault["instance"]["version"] = 0  # an unrelated fault the repair does not undo
    problems = validate.check_repair(second_fault, v)
    assert any("another reason" in p for p in problems), problems


def test_repair_rejects_unsupported_or_unresolved_operations() -> None:
    """`repair` accepts only add, remove and replace on paths that resolve."""
    for ops in ([{"op": "move", "from": "/a", "path": "/b"}],
                [{"op": "remove", "path": "/missing"}],
                [{"op": "replace", "path": "/a/9", "value": 1}],
                [{"op": "add", "path": "/a"}]):
        try:
            validate.apply_patch({"a": [1]}, ops)
        except ValueError:
            continue
        raise AssertionError(f"apply_patch accepted {ops}")
    assert validate.apply_patch({"a": [1]}, [{"op": "add", "path": "/a/-", "value": 2}]) == {"a": [1, 2]}


def test_crash_without_restart_rejected() -> None:
    """A crashed action must be followed by `restart` before the next action."""
    doc = {"script": [{"crash": {"at": "after_dispatch"}}, dict(_RUN, bind="$s"),
                      {"action": "run", "session": "$s", "principal": "p1", "input": []}]}
    assert any("without a `restart`" in p for p in validate.check_crashes(doc))
    ok = {"script": [{"crash": {"at": "after_dispatch"}}, dict(_RUN, bind="$s"), {"restart": {}},
                     {"action": "run", "session": "$s", "principal": "p1", "input": []}]}
    assert not validate.check_crashes(ok)


def test_crash_inside_concurrently_rejected() -> None:
    """A crash cannot arm an action inside `concurrently`; it must not silently
    attach to a later standalone action instead."""
    doc = {"script": [dict(_RUN, bind="$s"),
                      {"crash": {"at": "after_dispatch", "session": "$s"}},
                      {"concurrently": [{"action": "run", "session": "$s", "principal": "p1", "input": []},
                                        {"action": "cancel", "session": "$s"}]},
                      {"action": "run", "session": "$s", "principal": "p1", "input": []},
                      {"restart": {}}]}
    assert any("inside `concurrently`" in p for p in validate.check_crashes(doc))


def test_concurrent_sibling_binding_rejected() -> None:
    """Siblings in `concurrently` run at once: one may not use another's capture.
    An action with `startAfter` may use the `bind` of a sibling listed before it."""
    doc = {"script": [{"concurrently": [
        dict(_RUN, bind="$a", capture=[{"event": {"type": "run.started"}, "bind": {"runId": "$r"}}]),
        {"action": "cancel", "session": "$r"}]}]}
    assert any("$r" in p for p in validate.check_placeholders(doc))
    no_wait = {"script": [{"concurrently": [dict(_RUN, bind="$a"), {"action": "cancel", "session": "$a"}]}]}
    assert any("$a" in p for p in validate.check_placeholders(no_wait))
    waits = {"script": [{"concurrently": [dict(_RUN, bind="$a"),
                                          {"action": "cancel", "session": "$a", "startAfter": {"type": "tool.call"}}]}]}
    assert not validate.check_placeholders(waits)
    after = {"script": [{"concurrently": [dict(_RUN, bind="$a"), dict(_RUN, bind="$b")]},
                        {"action": "close", "session": "$a"}]}
    assert not validate.check_placeholders(after)


def test_matcher_misuse_rejected() -> None:
    """Unknown `$`-keys, malformed `$count`, and `$not` around `$contains` are errors."""
    for bad in ({"$contians": [1]},
                {"$count": {"of": {"$any": True}}},
                {"$count": {"of": {"$any": True}, "equals": 1, "gte": 0}},
                {"$not": {"$contains": [1]}}):
        assert validate.check_matchers({"expect": {"x": bad}}), bad
    assert not validate.check_matchers({"expect": {"x": {"$count": {"of": {"$any": True}, "equals": 1}}}})


def test_absent_under_unbound_placeholder_key_rejected() -> None:
    """A placeholder map key must be bound before `$absent` is applied under it."""
    doc = {"script": [], "expect": {"ports": {"idempotencyStore": {"t1": {"$k": {"$absent": True}}}}}}
    assert validate.check_placeholder_keys(doc)
    bound = {"script": [], "expect": {"a": {"key": "$k"}, "ports": {"idempotencyStore": {"t1": {"$k": {"$absent": True}}}}}}
    assert not validate.check_placeholder_keys(bound)


def test_unknown_stub_call_key_rejected() -> None:
    """`expect.stubCalls` keys must name a stub the fixture declares or a native binding."""
    doc = {"setup": {"config": {"base": "baseline"}, "stubs": {"tools": {"lookup": []}}},
           "script": [], "expect": {"stubCalls": {"no_such_tool": {"count": 0}}}}
    assert any("no_such_tool" in p for p in validate.check_stub_call_keys(doc))
    doc["expect"]["stubCalls"] = {"lookup": {"count": 0}}
    assert not validate.check_stub_call_keys(doc)


def test_stub_for_non_native_tool_rejected() -> None:
    """`stubs.tools` keys must be native-bound tool IDs in some loaded configuration."""
    doc = {"setup": {"config": {"base": "baseline"}, "stubs": {"tools": {"not_a_tool": []}}}, "script": []}
    assert any("not_a_tool" in p for p in validate.check_stub_call_keys(doc))


def test_port_case_foreign_op_rejected() -> None:
    """A port case may only call its own port's operations."""
    doc = {"port": "eventLog", "steps": [{"op": "save", "args": {}}]}
    assert validate.check_port_case(doc)
    assert not validate.check_port_case({"port": "eventLog", "steps": [{"op": "read", "args": {}}]})


def test_missing_merge_annotation_rejected() -> None:
    """CFG-030: removing a behavioural field's x-agentry-merge is caught."""
    from common import load_schemas
    schemas = copy.deepcopy(load_schemas())
    assert not validate.check_merge_annotations(schemas), "the real schemas should pass"
    sid = next(k for k in schemas if k.endswith("/config/harness-profile/v1.json"))
    del schemas[sid]["properties"]["stepLimit"]["x-agentry-merge"]
    assert any("stepLimit" in p for p in validate.check_merge_annotations(schemas))


def test_missing_secret_marker_rejected() -> None:
    """CFG-060, 061: a secretRef node without `x-agentry-secret: true` is caught."""
    from common import load_schemas
    schemas = copy.deepcopy(load_schemas())
    assert not validate.check_reference_markers(schemas), "the real schemas should pass"
    sid = next(k for k in schemas if k.endswith("/config/deployment/v1.json"))
    del schemas[sid]["$defs"]["credentials"]["additionalProperties"]["x-agentry-secret"]
    assert validate.check_reference_markers(schemas)


def test_invalid_inline_config_rejected() -> None:
    """Inline configuration expected to load must be schema-valid."""
    from common import load_schemas, registry
    schemas = load_schemas()
    reg = registry(schemas)
    tool = {"kind": "Tool", "id": "t", "version": 1, "schemaVersion": "0.1.0",
            "input": {"type": "object"}, "effect": "read", "binding": {"kind": "native", "handler": "test.t"}}
    doc = {"setup": {"config": {"base": "baseline", "artifacts": [tool]}}, "script": []}
    assert validate.check_inline_config(doc, schemas, reg), "a Tool without description loaded"


def main() -> int:
    tests = [test_unbound_placeholder_rejected, test_coverage_fails_when_last_fixture_removed,
             test_real_endpoint_rejected, test_invalid_example_needs_a_working_repair,
             test_repair_rejects_unsupported_or_unresolved_operations, test_crash_without_restart_rejected,
             test_crash_inside_concurrently_rejected, test_concurrent_sibling_binding_rejected,
             test_matcher_misuse_rejected, test_absent_under_unbound_placeholder_key_rejected,
             test_unknown_stub_call_key_rejected, test_stub_for_non_native_tool_rejected,
             test_port_case_foreign_op_rejected, test_missing_merge_annotation_rejected,
             test_missing_secret_marker_rejected, test_invalid_inline_config_rejected]
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
