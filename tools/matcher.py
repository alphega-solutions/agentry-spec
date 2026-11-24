"""Reference expectation matcher for conformance fixtures (EVAL-004).

This implements the matching semantics in conformance/README.md. The shared
conformance runner (tools/runner, ADR-0020) uses it, and any development-time
runner should agree with it:

- Objects written out in an expectation match partially: every listed key must
  match, unlisted keys of the actual value are ignored. Arrays written out
  match element by element and must have the same length.
- Matchers: $any, $absent, $regex, $len, $contains, $not, $every, $gte, $lte,
  $gt, $lt (whose argument may be a bound placeholder), $all, $count (and
  $selfProvider in adapter cases, given a value).
- Placeholders (`$name`) bind the whole value at their first match and must
  equal it exactly (deep equality) wherever they occur later. A placeholder
  may be a map key; it then binds to a key of the actual map.
- Assignments: `unordered`, `contains`, `subsequence` and `$contains` succeed
  when ANY valid assignment of items to distinct elements exists (order-
  preserving for `subsequence`). The search is exhaustive, never greedy.
  When several assignments exist, the bindings kept are those of the first in
  canonical order: items in listed order, each given the earliest element
  that still lets the remaining items match.
- Placeholders never bind inside $not, $count, $every or absentEvents; an
  unbound placeholder there is a fixture error (UnboundPlaceholder).

The matcher is a generator of binding environments in canonical order, so the
first environment it yields is the canonical one and backtracking is natural.

Run from the repository root: python tools/matcher_test.py
"""
from __future__ import annotations

import re
from typing import Any, Iterator

PLACEHOLDER = re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*$")
MATCHERS = {"$any", "$absent", "$regex", "$len", "$contains", "$not", "$every",
            "$gte", "$lte", "$gt", "$lt", "$all", "$count", "$selfProvider"}
_MISSING = object()

Env = dict[str, Any]


class UnboundPlaceholder(Exception):
    """A placeholder was used where it cannot bind (under $not, $count, $every
    or absentEvents) before anything bound it."""


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value not in MATCHERS and bool(PLACEHOLDER.match(value))


def _is_matcher(expected: Any) -> bool:
    return isinstance(expected, dict) and len(expected) >= 1 and all(k in MATCHERS for k in expected)


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


NUMBER_TOLERANCE = 1e-9  # fixture.yaml: numbers compare as decimals, absolute tolerance 1e-9


def _equal(a: Any, b: Any) -> bool:
    """Deep equality with JSON semantics: 1 == 1.0, but True != 1. Numbers
    are equal within an absolute tolerance of 1e-9 (fixture.yaml)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if _num(a) and _num(b):
        return abs(a - b) <= NUMBER_TOLERANCE
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


class Matcher:
    """Matches expectations against actual values. `self_provider` is the value
    `$selfProvider` stands for (adapter cases only)."""

    def __init__(self, self_provider: str | None = None):
        self.self_provider = self_provider

    # ---- public API -------------------------------------------------------

    def first(self, expected: Any, actual: Any, env: Env | None = None) -> Env | None:
        """The canonical binding environment if `actual` matches, else None."""
        return next(self.match(expected, actual, dict(env or {}), binding=True), None)

    def matches(self, expected: Any, actual: Any, env: Env | None = None) -> bool:
        return self.first(expected, actual, env) is not None

    # ---- core ---------------------------------------------------------------

    def match(self, expected: Any, actual: Any, env: Env, binding: bool) -> Iterator[Env]:
        """Yield every environment (extending `env`) under which `actual`
        matches `expected`, in canonical order. `actual` may be _MISSING."""
        if is_placeholder(expected):
            yield from self._placeholder(expected, actual, env, binding)
        elif _is_matcher(expected):
            yield from self._matchers(expected, actual, env, binding)
        elif actual is _MISSING:
            return
        elif isinstance(expected, dict):
            if isinstance(actual, dict):
                yield from self._object(list(expected.items()), actual, env, binding, set())
        elif isinstance(expected, list):
            if isinstance(actual, list) and len(actual) == len(expected):
                yield from self._sequence(expected, actual, env, binding)
        elif _equal(expected, actual):
            yield env

    def _placeholder(self, name: str, actual: Any, env: Env, binding: bool) -> Iterator[Env]:
        if actual is _MISSING:
            return
        if name in env:
            if _equal(env[name], actual):
                yield env
        elif binding:
            yield {**env, name: actual}
        else:
            raise UnboundPlaceholder(f"{name} is used where it cannot bind, before anything bound it")

    def _object(self, items: list, actual: dict, env: Env, binding: bool, used_keys: set) -> Iterator[Env]:
        if not items:
            yield env
            return
        (key, exp), rest = items[0], items[1:]
        if is_placeholder(key):
            yield from self._placeholder_key(key, exp, rest, actual, env, binding, used_keys)
            return
        if isinstance(exp, dict) and set(exp) == {"$absent"}:
            if exp["$absent"] is True and key not in actual:
                yield from self._object(rest, actual, env, binding, used_keys)
            return
        for e1 in self.match(exp, actual.get(key, _MISSING), env, binding):
            yield from self._object(rest, actual, e1, binding, used_keys | {key})

    def _placeholder_key(self, key: str, exp: Any, rest: list, actual: dict, env: Env,
                         binding: bool, used_keys: set) -> Iterator[Env]:
        absent = isinstance(exp, dict) and set(exp) == {"$absent"} and exp["$absent"] is True
        if key in env:
            bound = env[key]
            if absent:
                if bound not in actual:
                    yield from self._object(rest, actual, env, binding, used_keys)
                return
            for e1 in self.match(exp, actual.get(bound, _MISSING), env, binding):
                yield from self._object(rest, actual, e1, binding, used_keys | {bound})
            return
        if absent or not binding:
            raise UnboundPlaceholder(f"placeholder key {key} must be bound before it is used here")
        for k in actual:  # actual map order is the canonical order of candidate keys
            if k in used_keys:
                continue
            for e1 in self.match(exp, actual[k], {**env, key: k}, binding):
                yield from self._object(rest, actual, e1, binding, used_keys | {k})

    def _sequence(self, expected: list, actual: list, env: Env, binding: bool) -> Iterator[Env]:
        if not expected:
            yield env
            return
        for e1 in self.match(expected[0], actual[0], env, binding):
            yield from self._sequence(expected[1:], actual[1:], e1, binding)

    def assign(self, items: list, elements: list, env: Env, binding: bool,
               ordered: bool, used: frozenset = frozenset(), start: int = 0) -> Iterator[Env]:
        """Assign each item to a distinct element (in order when `ordered`),
        depth-first: items in listed order, elements earliest first."""
        if not items:
            yield env
            return
        for i in range(start if ordered else 0, len(elements)):
            if i in used:
                continue
            for e1 in self.match(items[0], elements[i], env, binding):
                yield from self.assign(items[1:], elements, e1, binding, ordered,
                                       used | {i}, i + 1 if ordered else 0)

    # ---- matchers -------------------------------------------------------------

    def _matchers(self, spec: dict, actual: Any, env: Env, binding: bool) -> Iterator[Env]:
        """All matcher keys in one object must hold (in listed order)."""
        def chain(keys: list, e: Env) -> Iterator[Env]:
            if not keys:
                yield e
                return
            for e1 in self._one(keys[0], spec[keys[0]], actual, e, binding):
                yield from chain(keys[1:], e1)
        yield from chain(list(spec), env)

    def _one(self, name: str, arg: Any, actual: Any, env: Env, binding: bool) -> Iterator[Env]:
        present = actual is not _MISSING
        if name == "$any":
            if present:
                yield env
        elif name == "$absent":
            if (arg is True) != present:
                yield env
        elif name == "$regex":
            if present and isinstance(actual, str) and re.search(arg, actual):
                yield env
        elif name == "$len":
            if is_placeholder(arg):  # a length observed earlier, like $gte/$lte
                if arg not in env:
                    raise UnboundPlaceholder(f"{arg} in $len must already be bound")
                arg = env[arg]
            if present and isinstance(actual, (list, str, dict)) and len(actual) == arg:
                yield env
        elif name in ("$gte", "$lte", "$gt", "$lt"):
            if is_placeholder(arg):  # compare with an observed value bound earlier
                if arg not in env:
                    raise UnboundPlaceholder(f"{arg} in {name} must already be bound")
                arg = env[arg]
            if present and _num(actual) and _num(arg) and (
                    (name == "$gte" and actual >= arg - NUMBER_TOLERANCE)
                    or (name == "$lte" and actual <= arg + NUMBER_TOLERANCE)
                    or (name == "$gt" and actual > arg + NUMBER_TOLERANCE)
                    or (name == "$lt" and actual < arg - NUMBER_TOLERANCE)):
                yield env
        elif name == "$contains":
            if present and isinstance(actual, list):
                yield from self.assign(list(arg), actual, env, binding, ordered=False)
        elif name == "$not":
            # Never binds: it matches whenever `arg` does not, absent included.
            if next(self.match(arg, actual, env, False), None) is None:
                yield env
        elif name == "$every":
            if present and isinstance(actual, list) and all(
                    next(self.match(arg, x, env, False), None) is not None for x in actual):
                yield env
        elif name == "$all":
            def chain(ms: list, e: Env) -> Iterator[Env]:
                if not ms:
                    yield e
                    return
                for e1 in self.match(ms[0], actual, e, binding):
                    yield from chain(ms[1:], e1)
            yield from chain(list(arg), env)
        elif name == "$count":
            if present and isinstance(actual, list):
                n = sum(1 for x in actual if next(self.match(arg["of"], x, env, False), None) is not None)
                if (("equals" in arg and n == arg["equals"]) or ("gte" in arg and n >= arg["gte"])
                        or ("lte" in arg and n <= arg["lte"])):
                    yield env
        elif name == "$selfProvider":
            if self.self_provider is None:
                raise ValueError("$selfProvider is only meaningful in adapter cases")
            if present and actual == self.self_provider:
                yield env

    # ---- event patterns (EVAL-004) -------------------------------------------

    def events(self, pattern: dict, events: list, env: Env | None = None) -> Env | None:
        """Match `expect.sessions.<s>.events` (`mode` + `items`) against a
        session's persisted events in log order. Returns the canonical
        environment, or None."""
        env = dict(env or {})
        mode, items = pattern.get("mode"), list(pattern.get("items") or [])
        if mode in ("sequence", "unordered") and not any(
                isinstance(it, dict) and it.get("type") == "checkpoint.saved" for it in items):
            events = [e for e in events if e.get("type") != "checkpoint.saved"]
        if mode == "sequence":
            gen = (self._sequence(items, events, env, True) if len(items) == len(events) else iter(()))
        elif mode == "unordered":
            gen = (self.assign(items, events, env, True, ordered=False)
                   if len(items) == len(events) else iter(()))
        elif mode == "contains":
            gen = self.assign(items, events, env, True, ordered=False)
        elif mode == "subsequence":
            gen = self.assign(items, events, env, True, ordered=True)
        else:
            raise ValueError(f"unknown event-pattern mode {mode!r}")
        return next(gen, None)

    def absent_events(self, patterns: list, events: list, env: Env) -> list:
        """The `absentEvents` patterns that some event matches (violations).
        Placeholders here never bind, so they must already be bound."""
        return [p for p in patterns
                if any(next(self.match(p, e, env, False), None) is not None for e in events)]
