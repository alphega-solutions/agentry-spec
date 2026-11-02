"""Spec-CI self-tests: the checks EVAL-002 and EVAL-010 require of the
validator and the coverage tool are exercised on deliberately broken inputs.

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


def main() -> int:
    tests = [test_unbound_placeholder_rejected, test_coverage_fails_when_last_fixture_removed]
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
