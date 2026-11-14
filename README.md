# ActionLock_Extension1

Review the outcome of an authorised DynamoDB table change. This read-only companion links the AWS request to an ActionLock decision receipt and compares the attempt with a separate observation of the target table.

## Try the synthetic protected-table case

Requires Python 3.11 or newer. From the repository root:

```sh
python -m extension1 examples/protected-table.json
python -m unittest discover -s tests -v
```

The example records a refused deletion followed by a read showing that the table was present. A delayed event or an inconclusive read leaves the outcome pending. The JSON identifies the source, operation, account, region, target and timestamps. A successful CLI exit means a report was produced.

The standalone example uses supplied evidence. The optional live observer uses boto3, STS GetCallerIdentity and DynamoDB DescribeTable with a customer-managed read-only AWS profile. No AWS access is needed for development or CI.

## Read the evidence

```sh
python -m extension1 examples/protected-table.json --format text
```

| Question | Evidence used |
| --- | --- |
| What did the human authorise? | An optional signed ActionLock decision supplies the contract ID, approvers, plan digest and target. The demo explicitly labels its supplied input. |
| What existed beforehand? | A timestamped baseline from the same account, region and table. A denied read is labelled unreadable. |
| What did AWS do? | CloudTrail management events must match the service, operation, target, account, region, decision window and receipt's source identity. A generic access denial establishes only that AWS refused the request. |
| What state was later observed? | A separate DescribeTable read after the matched attempt. An active table, a missing table, a transition and an unreadable resource have different meanings. |

For customer-managed collection, install boto3 (or the package's optional `aws` extra) and select the intended read-only AWS profile. Use the commercial AWS partition. The three commands below are for your own case file and scoped AWS account.

```sh
python -m extension1 evidence.json --snapshot
python -m extension1 evidence.json --lookup-events --observe --format text
python -m extension1 evidence.json --format json
```

Capture the snapshot before the decision and supply its JSON as the optional `baseline`. The second command looks up regional CloudTrail management events and takes a fresh resource read. Re-run after event delivery if the result is pending. The last command replays the supplied evidence offline. Input from disk is trusted by the operator. Store raw evidence separately and keep real evidence files outside the repository.

### Investigate a pending result

- Check the receipt, AWS region, table name and operation when no event matched. Multiple different attempt outcomes remain visible as mixed.
- Check the observation time and table status. The read must follow the last matching attempt before it can support a conclusion.
- Inspect the collection window if the CLI reports incomplete history. A page limit or lookup error stops the review. A later table state alone cannot establish which caller caused it.

The optional [ActionLock integration](integration/README.md) adds tag-scoped contracts, durable decision export and the verified-receipt adapter. The extension uses the existing approval and execution path. Local tests use synthetic AWS clients and fixtures. Customer evaluations and live validation of this extension remain open.

## Run the pilot cases

```sh
python -m extension1.pilot examples/pilot.json
```

The ten labelled synthetic cases cover a protected table, successful operations, delayed events, stale reads, unreadable state and conflicting observations. The command prints the expected and actual outcome for each case and exits with status 1 on a mismatch. The signed-contract integration tests also exercise ten pairs where the same plan is checked against two different tag scopes. Neither set measures real-world effectiveness.

## Installation and verification

```sh
python -m pip install .
actionlock-evidence examples/protected-table.json --format text
# Optional AWS reader in a customer-managed environment
python -m pip install '.[aws]'
```

CI exercises offline replay with Python 3.11, 3.12 and 3.13. To reproduce the full integration checks locally, use the pinned upstream revision and commands in the integration guide. The public CI job needs no AWS credentials or private upstream access.
