"""The shared conformance runner (ADR-0020, EVAL-020/021/023).

    python tools/runner/run.py --driver "python my_driver.py" [--fixtures GLOB ...]
                               [--report report.json] [--junit report.xml]

Runs the fixtures through the driver and writes the conformance report
(schemas/eval/v1/conformance-report.yaml) and JUnit XML. Exits 0 only if the
report conforms.
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

from runner.client import DriverClient, DriverError  # noqa: E402
from runner.engine import FixtureRun, Unmet  # noqa: E402

RUNNER_VERSION = "0.1.0"


def fixture_paths(globs: list[str]) -> list[pathlib.Path]:
    base = ROOT / "conformance"
    paths: list[pathlib.Path] = []
    for g in globs:
        paths += sorted(p for p in base.glob(g) if p.suffix == ".yaml")
    skip = {"schema", "shared", "golden", "ports", "adapters", "cel"}
    return [p for p in dict.fromkeys(paths)
            if len(p.relative_to(base).parts) > 1 and p.relative_to(base).parts[0] not in skip]


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
            skip_for = next((f for f in res["features"] if f in unsupported), None)
            if skip_for:
                res.update(status="skipped", skippedFor=skip_for)
            else:
                try:
                    FixtureRun(client, doc).execute()
                    res["status"] = "pass"
                except Unmet as exc:
                    res.update(status="fail", firstUnmet=str(exc))
                except DriverError as exc:
                    res.update(status="fail", firstUnmet=f"driver: {exc}")
            results.append(res)
    finally:
        client.close()
    impl = info.get("implementation") or {}
    return {
        "schemaVersion": "0.1.0",
        "implementation": impl.get("name", "unknown"),
        "runner": {"version": RUNNER_VERSION},
        "driver": {"protocol": info.get("protocol", "1.0"), "implementationVersion": impl.get("version", "unknown"),
                   "language": impl.get("language", "unknown")},
        "contract": info.get("contract", "0.1.0"),
        "unsupportedFeatures": unsupported,
        "results": results,
        "conforms": all(r["status"] != "fail" for r in results),
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
    ap.add_argument("--fixtures", nargs="*", default=["**/*.yaml"], help="globs relative to conformance/")
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
    print(f"conforms: {report['conforms']}")
    return 0 if report["conforms"] else 1


if __name__ == "__main__":
    sys.exit(main())
