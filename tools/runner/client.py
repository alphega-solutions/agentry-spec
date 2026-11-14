"""JSON-RPC 2.0 client for a conformance driver over stdio (conformance/schema/driver.yaml)."""
from __future__ import annotations

import json
import subprocess
from typing import Any


class DriverError(Exception):
    """The driver returned a JSON-RPC error or broke the protocol: a driver fault,
    never a harness outcome."""


class DriverClient:
    def __init__(self, command: list[str]):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)
        self._next = 1

    def call(self, method: str, params: dict | None = None) -> Any:
        req = {"jsonrpc": "2.0", "id": self._next, "method": method, "params": params or {}}
        self._next += 1
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise DriverError(f"driver exited during {method}")
        try:
            resp = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DriverError(f"driver wrote non-JSON to stdout during {method}") from exc
        if resp.get("id") != req["id"] or resp.get("jsonrpc") != "2.0":
            raise DriverError(f"driver response to {method} has the wrong id or version")
        if "error" in resp:
            err = resp["error"] or {}
            raise DriverError(f"{method}: driver error {err.get('code')}: {err.get('message')}")
        return resp.get("result")

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
