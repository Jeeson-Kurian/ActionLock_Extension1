"""Command-line entry point for offline replay and read-only AWS evidence collection."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .evidence import observe_table, review, validate


def unique(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("Duplicate JSON field")
    return obj


def main():
    parser = argparse.ArgumentParser(description="Review trusted evidence for a single DynamoDB table operation.")
    parser.add_argument("case", type=Path)
    parser.add_argument("--observe", action="store_true", help="Take a fresh AWS read using boto3 and your read-only profile")
    parser.add_argument("--snapshot", action="store_true",
                        help="Capture a read-only table observation for use as a baseline")
    parser.add_argument("--lookup-events", action="store_true",
                        help="Collect regional CloudTrail management events for the decision window")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--receipts", type=Path, help="Read the target and approvals from a signed ActionLock log")
    parser.add_argument("--receipt-id")
    parser.add_argument("--address")
    args = parser.parse_args()
    if args.snapshot and (args.observe or args.lookup_events or args.format != "json"):
        parser.error("--snapshot outputs one JSON observation and is a separate collection mode")
    selectors = (args.receipts, args.receipt_id, args.address)
    if any(selectors) and not all(selectors):
        parser.error("--receipts, --receipt-id and --address must be used together")
    try:
        case = json.loads(args.case.read_text(encoding="utf-8"), object_pairs_hook=unique)
        approval = None
        if args.receipts:
            from .receipts import decision_target
            target, approval = decision_target(args.receipts, args.receipt_id, args.address)
        else:
            target = case["target"]
        validate(target)
        if args.observe or args.lookup_events or args.snapshot:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
            try:
                session = boto3.Session(region_name=target["region"])
                if session.client("sts").get_caller_identity()["Account"] != target["account"]:
                    raise ValueError("AWS observer account mismatch")
                if args.snapshot:
                    print(json.dumps(observe_table(session.client("dynamodb"), target), indent=2))
                    return
                if args.lookup_events:
                    from .cloudtrail import lookup_events
                    until = datetime.now(timezone.utc).isoformat()
                    case["events"] = lookup_events(session.client("cloudtrail"), target, until)
                if args.observe:
                    case["observation"] = observe_table(session.client("dynamodb"), target)
                case["as_of"] = datetime.now(timezone.utc).isoformat()
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "unknown")
                raise ValueError(f"AWS collection failed ({code}). Check the profile, region and permissions.") from exc
            except BotoCoreError as exc:
                raise ValueError(f"AWS client unavailable ({type(exc).__name__}). Check the profile and connection.") from exc
        report = review(target, case["events"], case.get("observation"), as_of=case["as_of"])
        report["authority_source"] = "verified_decision_receipt" if approval else "supplied_input"
        report["approval"] = approval
        if "baseline" in case:
            from .evidence import check_baseline
            report["baseline"] = check_baseline(target, case["baseline"])
        if args.format == "text":
            from .report import render
            print(render(report))
        else:
            print(json.dumps(report, indent=2))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, ImportError) as exc:
        parser.exit(2, f"Unable to review evidence: {exc}\n")


if __name__ == "__main__":
    main()
