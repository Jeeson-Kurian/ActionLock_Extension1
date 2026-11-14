"""Replay labelled synthetic cases. This checks regressions and makes no customer performance claim."""
import argparse
import json
from pathlib import Path

from .evidence import review


def replay(cases):
    for case in cases:
        report = review(case["target"], case["events"], case["observation"], as_of=case["as_of"])
        expected = case["expected"]
        actual = {key: report[key] for key in ("aws_attempt", "outcome")}
        yield {"case": case["name"], "expected": expected, "actual": actual, "passed": actual == expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    if not isinstance(cases, list) or not cases:
        parser.error("At least one labelled case is required")
    results = list(replay(cases))
    print(json.dumps({"cases": results, "passed": sum(r["passed"] for r in results), "total": len(results)}, indent=2))
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
