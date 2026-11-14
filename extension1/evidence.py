"""Correlate one DynamoDB lifecycle action with scoped CloudTrail and DescribeTable evidence."""
from datetime import datetime, timezone
import re


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("A timestamp is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed.astimezone(timezone.utc)


def validate(target):
    if set(target) != {"receipt", "account", "region", "table", "operation", "started_at"}:
        raise ValueError("Unexpected target fields")
    if target["operation"] not in {"DeleteTable", "CreateTable"}:
        raise ValueError("Only DynamoDB table create/delete have defined postconditions")
    if not re.fullmatch(r"[0-9]{12}", target["account"]):
        raise ValueError("Invalid account")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z0-9]+)+-[0-9]+", target["region"]):
        raise ValueError("Invalid region")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,255}", target["table"]):
        raise ValueError("Invalid table")
    if not re.fullmatch(r"al-[a-zA-Z0-9_.-]+", target["receipt"]):
        raise ValueError("Invalid receipt")
    timestamp(target["started_at"])


def observe_table(client, target, clock=lambda: datetime.now(timezone.utc)):
    """Caller supplies a read-only regional client whose account has been verified."""
    validate(target)
    base = {k: target[k] for k in ("account", "region", "table")}
    arn = f"arn:aws:dynamodb:{target['region']}:{target['account']}:table/{target['table']}"
    try:
        table = client.describe_table(TableName=target["table"])["Table"]
        state = "unknown"
        if table.get("TableArn") == arn:
            state = "present" if table.get("TableStatus") == "ACTIVE" else "transitioning"
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code == "ResourceNotFoundException":
            state = "absent"
        elif code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            state = "unreadable"
        else:
            state = "unknown"
    return {**base, "state": state, "observed_at": clock().isoformat()}


def review(target, events, observation, *, as_of):
    """Inputs come from a trusted collector. Missing or conflicting evidence remains explicit."""
    validate(target)
    started, cutoff = timestamp(target["started_at"]), timestamp(as_of)
    if cutoff < started:
        raise ValueError("Review predates decision")
    if not isinstance(events, list):
        raise ValueError("Expected a list of CloudTrail records")
    matched = {}
    for event in events:
        context = (event.get("userIdentity") or {}).get("sessionContext") or {}
        if (context.get("sourceIdentity") != target["receipt"]
                or event.get("eventSource") != "dynamodb.amazonaws.com"
                or event.get("eventName") != target["operation"]
                or event.get("recipientAccountId") != target["account"]
                or event.get("awsRegion") != target["region"]
                or (event.get("requestParameters") or {}).get("tableName") != target["table"]):
            continue
        at = timestamp(event["eventTime"])
        if not started <= at <= cutoff:
            continue
        event_id = event.get("eventID")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Matched event lacks an ID")
        code = event.get("errorCode")
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            attempt = "denied"
        elif code or event.get("errorMessage"):
            attempt = "failed"
        else:
            attempt = "accepted"
        record = {"id": event_id, "time": event["eventTime"], "attempt": attempt}
        if event_id in matched and matched[event_id] != record:
            raise ValueError("Conflicting copies of the same CloudTrail event")
        matched[event_id] = record
    records = sorted(matched.values(), key=lambda r: (timestamp(r["time"]), r["id"]))
    attempts = {r["attempt"] for r in records}
    attempt = next(iter(attempts)) if len(attempts) == 1 else ("mixed" if records else "pending")
    expected = "absent" if target["operation"] == "DeleteTable" else "present"
    state, observed = "unknown", None
    if observation is not None:
        if set(observation) != {"account", "region", "table", "state", "observed_at"}:
            raise ValueError("Unexpected observation fields")
        if any(observation.get(k) != target[k] for k in ("region", "account", "table")):
            raise ValueError("Observation target differs from authorised target")
        state, observed = observation["state"], observation["observed_at"]
        if state not in {"unknown", "absent", "present", "unreadable", "transitioning"}:
            raise ValueError("Invalid observation")
        observed_time = timestamp(observed)
        if observed_time > cutoff:
            raise ValueError("Observation is after review time")
    checkpoint = timestamp(records[-1]["time"]) if records else started
    # Both evidence sources must support the conclusion. Preserve earlier reads as context.
    fresh = observed is not None and timestamp(observed) > checkpoint
    outcome = "pending"
    if fresh and state in {"present", "absent"}:
        if attempt == "accepted":
            outcome = "expected_state_observed" if state == expected else "state_differs"
        elif attempt == "denied":
            outcome = "denial_and_opposite_state_observed" if state != expected else "conflicting_evidence"
    return {"target": target, "reviewed_at": as_of, "expected_state": expected, "aws_attempt": attempt,
            "enforcement_layer": "AWS (specific policy unverified)" if attempt == "denied" else None,
            "observation": observation, "events": records, "outcome": outcome}
