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
    parser.add_argument("--receipts", type=Path, help="Read the target and approvals from a signed ActionLock log")
    parser.add_argument("--receipt-id")
    parser.add_argument("--address")
    args = parser.parse_args()
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
        if args.observe:
            import boto3
            session = boto3.Session(region_name=target["region"])
            if session.client("sts").get_caller_identity()["Account"] != target["account"]:
                raise ValueError("AWS observer account mismatch")
            case["observation"] = observe_table(session.client("dynamodb"), target)
            case["as_of"] = datetime.now(timezone.utc).isoformat()
        report = review(target, case["events"], case.get("observation"), as_of=case["as_of"])
        report["authority_source"] = "verified_decision_receipt" if approval else "supplied_input"
        report["approval"] = approval
        print(json.dumps(report, indent=2))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, ImportError) as exc:
        parser.exit(2, f"Unable to review evidence: {exc}\n")


if __name__ == "__main__":
    main()
