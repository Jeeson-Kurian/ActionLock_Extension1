# Connect an existing ActionLock runner

This optional patch targets ActionLock commit `c60bd652ff48d4e565ae64a4c44af9eb310f7931`. Use a separate checkout with the two project directories side by side. Run from the extension repository on Linux.

```sh
git -C ../ActionLock apply --check "$PWD/integration/actionlock.patch"
git -C ../ActionLock apply "$PWD/integration/actionlock.patch"
PYTHONPATH=".:../ActionLock:../ActionLock/tests" python -m unittest discover -s integration -v
(cd ../ActionLock && python -m unittest discover -s tests -v)
```

The patch makes three changes at the upstream boundaries.

1. A human signing an update-only contract can specify `"allowed_tag_keys": ["Owner"]`. The verifier compares Terraform's tag representations, checks other attributes and escalates an unverifiable or broader update through the existing approval process. Existing contracts retain the same signed representation.
2. The runner consumes an approval and queues the corresponding decision in one SQLite transaction. Export runs before credential acquisition. Local POSIX file locking serialises receipt writers. To recover a pending decision, use the same database, receipt log and backend signing configuration with `python -m actionlock export-decisions --database requests.db --receipts receipts.jsonl`. This recovers evidence without reapplying the plan.
3. A verified decision records supported DynamoDB targets. The sandbox collector treats an explicit table-not-found result separately from denied or inconclusive reads. The evidence reviewer can derive the target and approvers from the signed log.

To use verified decisions, set the patched checkout on PYTHONPATH **inside the trusted backend** with its existing signing configuration. Then run:

```sh
python -m extension1 evidence.json --receipts receipts.jsonl --receipt-id RECEIPT_ID --address aws_dynamodb_table.orders --format text
```

A pre-execution refusal is recorded by ActionLock's verifier. Only consumed decisions can have AWS execution evidence. Keep the verifier trace for pre-execution cases. Do not give a proposal-generating agent access to the backend signing key.
