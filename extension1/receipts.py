"""Adapter for the local, verified ActionLock receipt chain."""


def decision_target(path, receipt_id, address):
    from actionlock.contract import HmacSigner
    from actionlock.receipts import ReceiptLog

    log = ReceiptLog(path, HmacSigner.from_environment())
    # Work from one immutable snapshot of the bytes read, even if the log is growing.
    class Snapshot(ReceiptLog):
        def entries(self):
            return entries

    entries = log.entries()
    Snapshot(log.path, log.signer).verify()
    found = [r for r in entries if r["receipt_id"] == receipt_id and r["kind"] == "decision"]
    if len(found) != 1:
        raise ValueError("Expected one verified decision receipt")
    decision = found[0]
    fields = decision["fields"]
    targets = [t for t in fields.get("targets", []) if t["address"] == address]
    if len(targets) != 1:
        raise ValueError("Decision has no unique supported target for that address")
    target = targets[0]
    apply_rows = [row for row in entries if row["kind"] == "apply"
                  and row["fields"].get("decision_receipt") == receipt_id]
    if len(apply_rows) > 1:
        raise ValueError("Multiple apply receipts reference this decision")
    runner_result = {"status": "pending"}
    if apply_rows:
        row = apply_rows[0]
        details = row["fields"]
        if details.get("applied") is True:
            status = "apply_completed"
        elif isinstance(details.get("exit_code"), int):
            status = "apply_failed_possibly_partial"
        else:
            status = "runner_refused"
        runner_result = {"status": status, "observed_at": row["created_at"], "receipt_id": row["receipt_id"]}
    target_fields = {
        "receipt": receipt_id, "account": fields["aws_account_id"], "region": fields["region"],
        "table": target["table"], "operation": target["operation"], "started_at": decision["created_at"],
    }
    approval = {
        "contract_id": fields["contract_id"], "plan_digest": fields["plan_digest"],
        "outcome": fields["outcome"], "approvers": fields["approvers"], "address": address,
        "runner_result": runner_result,
    }
    return target_fields, approval
