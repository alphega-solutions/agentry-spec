"""A fake conformance driver for testing the shared runner (ADR-0020).

It runs no harness. It answers `replay` actions from the golden bundle it is
given, rewriting the recording into a new session as a conforming harness
would (EVAL-060, EVAL-062 and their Area 11 readings):
- a new session ID, run IDs and event IDs;
- `session.created` names the recording (`replay: {sessionId, snapshotHash}`);
- an agent-bound call answered from the recording carries no `childSessionId`;
- no provider is called and no tool is dispatched.

Every other action is answered with a JSON-RPC error ("not supported"), so
the runner reports those fixtures as failing rather than passing vacuously.

Set AGENTRY_FAKE_DRIVER_FAULT=tool-output to corrupt tool results, so the
runner's self-tests can check that a wrong implementation fails.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import uuid

FAULT = os.environ.get("AGENTRY_FAKE_DRIVER_FAULT", "")


class FakeDriver:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.ports = {"eventLog": {}, "checkpointStore": {}, "idempotencyStore": {}, "snapshotStore": {},
                      "blobStore": {}, "auditLog": {}}
        self.pending: dict[str, tuple[str, dict]] = {}
        self.now = "2026-01-01T00:00:00Z"
        self.counter = 0

    def _id(self) -> str:
        self.counter += 1
        return str(uuid.UUID(f"01900000-0000-7000-8000-{self.counter:012x}"))

    # ---- methods ------------------------------------------------------------

    def describe(self, _p: dict) -> dict:
        return {"protocol": "1.0", "contract": "0.1.0",
                "implementation": {"name": "agentry-fake-driver", "version": "0.0.0", "language": "python"},
                "unsupportedFeatures": [], "crashPoints": []}

    def fixture_begin(self, p: dict) -> dict:
        self.reset()
        self.now = (p.get("setup") or {}).get("clock", self.now)
        return {}

    def action_start(self, p: dict) -> dict:
        self.pending[p["requestId"]] = (p["action"], p.get("args") or {})
        return {}

    def settle(self, _p: dict) -> dict:
        events, completed = [], []
        for rid, (action, args) in list(self.pending.items()):
            del self.pending[rid]
            if action != "replay":
                raise NotImplementedError(f"the fake driver does not support `{action}`")
            outcome, new_events = self._replay(args)
            events += [{"process": "main", "requestId": rid, "event": e} for e in new_events]
            outcome["newEvents"] = len(new_events)
            completed.append({"requestId": rid, "outcome": outcome})
        return {"now": self.now, "events": events, "completed": completed, "crashed": [], "waiting": []}

    def observe(self, p: dict) -> dict:
        out: dict = {}
        for item in p.get("items") or []:
            if item == "ports":
                out["ports"] = copy.deepcopy(self.ports)
            elif item in ("stubCalls", "providerRequests", "delivered"):
                out[item] = {}
            elif item == "telemetrySpans":
                out[item] = []
            elif item == "events":
                out[item] = {sid: evs for t in self.ports["eventLog"].values() for sid, evs in t.items()}
        return out

    # ---- replay -------------------------------------------------------------

    def _replay(self, args: dict) -> tuple[dict, list]:
        bundle, tenant = args["bundle"], args["tenant"]
        old_sid, sid = bundle["sessionId"], self._id()
        runs: dict[str, str] = {}
        events = []
        for e in bundle["events"]:
            if e.get("sessionId") != old_sid:
                continue
            e = copy.deepcopy(e)
            e["sessionId"], e["eventId"], e["tenantId"] = sid, self._id(), tenant
            if "runId" in e:
                e["runId"] = runs.setdefault(e["runId"], self._id())
            payload = e.get("payload") or {}
            if e["type"] == "session.created":
                payload["replay"] = {"sessionId": old_sid, "snapshotHash": e["snapshotHash"]}
            if e["type"] == "tool.call":
                payload.pop("childSessionId", None)
            if e["type"] == "tool.result" and FAULT == "tool-output":
                e["payload"] = json.loads(json.dumps(payload).replace("SYN-VALUE", "SYN-WRONG"))
            events.append(e)
        state, reason = "idle", None
        for e in events:
            if e["type"] == "run.ended":
                state = "suspended" if e["payload"].get("reason") == "escalated" else "idle"
            if e["type"] == "session.closed":
                state, reason = "closed", e["payload"].get("reason")
        self.ports["eventLog"].setdefault(tenant, {})[sid] = events
        cp = {"sessionId": sid, "tenant": tenant, "state": state, "snapshotHash": events[0]["snapshotHash"]}
        if reason:
            cp["closeReason"] = reason
        self.ports["checkpointStore"].setdefault(tenant, {})[sid] = cp
        return {"ok": True, "sessionId": sid, "divergences": []}, events


def main() -> int:
    d = FakeDriver()
    methods = {"driver.describe": d.describe, "fixture.begin": d.fixture_begin, "action.start": d.action_start,
               "settle": d.settle, "observe": d.observe, "fixture.end": lambda p: {}}
    for line in sys.stdin:
        req = json.loads(line)
        try:
            fn = methods.get(req["method"])
            if fn is None:
                raise NotImplementedError(f"the fake driver does not support `{req['method']}`")
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": fn(req.get("params") or {})}
        except NotImplementedError as exc:
            resp = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": str(exc)}}
        except Exception as exc:  # noqa: BLE001 - report any fault as a driver error
            resp = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32000, "message": repr(exc)}}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
