"""The shared conformance runner (ADR-0020, EVAL-020/021/023).

    python tools/runner/run.py --driver "python my_driver.py" [--fixtures GLOB ...]
                               [--report report.json] [--junit report.xml]

Runs the fixtures through the driver and writes the conformance report
(schemas/eval/v1/conformance-report.yaml) and JUnit XML. Exits 0 if no
fixture failed. `conforms` (the claim, EVAL-023) is true only for a run of
the full suite with no failures; while some fixture kinds are not yet run
(NOT_YET_RUN), no run is a full suite, so no run claims conformance.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shlex
import sys
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from common import ROOT, load_yaml  # noqa: E402

from runner.cases import run_adapter_case, run_cel_case, run_port_case  # noqa: E402
from runner.client import DriverClient, DriverError  # noqa: E402
from runner.engine import FixtureRun, Unmet  # noqa: E402

RUNNER_VERSION = "0.1.0"
FULL_SUITE = ["**/*.yaml"]
NOT_YET_RUN: list[str] = []  # fixture kinds the runner does not execute yet


def fixture_paths(globs: list[str]) -> list[pathlib.Path]:
    base = ROOT / "conformance"
    paths: list[pathlib.Path] = []
    for g in globs:
        paths += sorted(p for p in base.glob(g) if p.suffix == ".yaml")
    skip = {"schema", "shared", "golden", *NOT_YET_RUN}

    def wanted(p: pathlib.Path) -> bool:
        parts = p.relative_to(base).parts
        if len(parts) < 2 or parts[0] in skip:
            return False
        if parts[0] == "adapters":  # only adapters/cases/*.yaml are cases; manifests and transcripts are data
            return len(parts) == 3 and parts[1] == "cases"
        return True
    return [p for p in dict.fromkeys(paths) if wanted(p)]


def _kind(path: pathlib.Path) -> str:
    top = path.relative_to(ROOT / "conformance").parts[0]
    return {"ports": "port", "adapters": "adapter", "cel": "cel"}.get(top, "fixture")


def run(driver: list[str], globs: list[str]) -> dict:
    client = DriverClient(driver)
    try:
        info = client.call("driver.describe", {})
        unsupported = list(info.get("unsupportedFeatures") or [])
        results = []
        for path in fixture_paths(globs):
            doc = load_yaml(path)
            res = {"fixture": doc["id"], "requirements": list(doc.get("requirements") or []),
                   "features": list(doc.get("features") or [])}
            kind = _kind(path)
            if kind == "port":
                targets = list((info.get("portAdapters") or {}).get(doc["port"]) or [])
            elif kind == "adapter":
                targets = list(info.get("providerAdapters") or [])
            else:
                targets = [None]
            if not targets:  # a driver must offer at least one adapter for every port and provider case
                results.append({**res, "status": "fail",
                                "firstUnmet": f"driver: no {'port' if kind == 'port' else 'provider'} adapter offered for this case"})
                continue
            for target in targets:
                r = dict(res, fixture=f"{doc['id']}@{target}" if target else doc["id"])
                skip_for = next((f for f in r["features"] if f in unsupported), None)
                if skip_for:
                    r.update(status="skipped", skippedFor=skip_for)
                    results.append(r)
                    continue
                try:
                    if kind == "port":
                        run_port_case(client, doc, target)
                    elif kind == "adapter":
                        run_adapter_case(client, doc, target)
                    elif kind == "cel":
                        run_cel_case(client, doc)
                    else:
                        FixtureRun(client, doc).execute()
                    r["status"] = "pass"
                except Unmet as exc:
                    r.update(status="fail", firstUnmet=str(exc))
                except DriverError as exc:
                    r.update(status="fail", firstUnmet=f"driver: {exc}")
                results.append(r)
    finally:
        client.close()
    impl = info.get("implementation") or {}
    return {
        "schemaVersion": "0.1.0",
        "implementation": impl.get("name", "unknown"),
        "runner": {"version": RUNNER_VERSION},
        "driver": {"protocol": info.get("protocol", "unknown"), "implementationVersion": impl.get("version", "unknown"),
                   "language": impl.get("language", "unknown")},
        "contract": info.get("contract", "0.1.0"),
        "unsupportedFeatures": unsupported,
        "results": results,
        "conforms": (all(r["status"] != "fail" for r in results)
                     and list(globs) == FULL_SUITE and not NOT_YET_RUN),
    }


def junit(report: dict) -> str:
    rs = report["results"]
    fails = sum(r["status"] == "fail" for r in rs)
    skips = sum(r["status"] == "skipped" for r in rs)
    out = [f'<testsuite name={quoteattr(report["implementation"])} tests="{len(rs)}" failures="{fails}" skipped="{skips}">']
    for r in rs:
        out.append(f"  <testcase name={quoteattr(r['fixture'])}>")
        out.append("    <properties>" + "".join(
            f'<property name="requirement" value={quoteattr(q)}/>' for q in r["requirements"]) + "</properties>")
        if r["status"] == "fail":
            out.append(f"    <failure message={quoteattr(r['firstUnmet'][:200])}>{escape(r['firstUnmet'])}</failure>")
        elif r["status"] == "skipped":
            out.append(f"    <skipped message={quoteattr(r['skippedFor'])}/>")
        out.append("  </testcase>")
    out.append("</testsuite>")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--driver", required=True, help="command that starts the driver")
    ap.add_argument("--fixtures", nargs="*", default=FULL_SUITE, help="globs relative to conformance/")
    ap.add_argument("--report")
    ap.add_argument("--junit")
    args = ap.parse_args()
    report = run(shlex.split(args.driver), args.fixtures)
    if args.report:
        pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    if args.junit:
        pathlib.Path(args.junit).write_text(junit(report))
    for r in report["results"]:
        print(f"{r['status']:7} {r['fixture']}" + (f": {r['firstUnmet']}" if r["status"] == "fail" else ""))
    failed = sum(r["status"] == "fail" for r in report["results"])
    print(f"failed: {failed}; conforms: {report['conforms']}"
          + ("" if report["conforms"] or failed else " (not a full-suite run, or some fixture kinds are not run yet)"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
