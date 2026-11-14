"""Collect a bounded window of DynamoDB management events for one review."""

from .evidence import timestamp, validate
from .json_input import load_evidence_json


class IncompleteHistory(ValueError):
    """The requested window could not be read completely."""


def lookup_events(client, target, until, *, page_limit=20):
    validate(target)
    start, end = timestamp(target["started_at"]), timestamp(until)
    if start > end:
        raise ValueError("Collection window ends before the decision")
    paginator = client.get_paginator("lookup_events")
    pages = paginator.paginate(
        StartTime=start,
        EndTime=end,
        LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": target["operation"]}],
        PaginationConfig={"PageSize": 50},
    )
    collected = []
    for index, page in enumerate(pages, start=1):
        if index > page_limit or (index == page_limit and page.get("NextToken")):
            raise IncompleteHistory("Collection limit reached. Review a shorter time window.")
        if not isinstance(page.get("Events"), list):
            raise IncompleteHistory("CloudTrail returned a page without an event list")
        for entry in page["Events"]:
            event = load_evidence_json(entry["CloudTrailEvent"])
            if not isinstance(event, dict):
                raise IncompleteHistory("CloudTrail returned an invalid management event")
            collected.append(event)
    return collected
