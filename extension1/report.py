"""Human-readable rendering of the same evidence used for JSON output."""
def render(report):
    target = report["target"]
    observed = report["observation"]
    lines = [
        f"{target['operation']} · {target['table']}",
        f"Account {target['account']} · {target['region']} · receipt {target['receipt']}",
        f"Decision time: {target['started_at']} · authority: {report['authority_source']}",
    ]
    if report["approval"]:
        approval = report["approval"]
        people = ", ".join(approval["approvers"]) or "covered by signed task contract"
        lines.append(f"Contract {approval['contract_id']} · verdict {approval['outcome']} · approval: {people}")
        lines.append(f"Runner result: {approval['runner_result']['status']}")
    if report.get("baseline"):
        baseline = report["baseline"]
        lines.append(f"Before execution: {baseline['state']} at {baseline['observed_at']}")
    for event in report["events"]:
        lines.append(f"AWS attempt: {event['attempt']} at {event['time']} (event {event['id']})")
    if not report["events"]:
        lines.append("AWS attempt: awaiting a matching event")
    if observed:
        lines.append(f"Independent read: {observed['state']} at {observed['observed_at']}")
    else:
        lines.append("Independent read: awaiting an observation")
    lines.append(f"Expected state: {report['expected_state']} · conclusion: {report['outcome']}")
    if report["outcome"] == "pending":
        lines.append("Review pending. Check for delayed events, mixed attempts or a newer conclusive read.")
    return "\n".join(lines)
