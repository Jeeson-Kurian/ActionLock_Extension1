# Reproduce an outcome review

The fixtures use a fictitious AWS account, resource and receipt. Times are fixed so a rerun gives the same result.

| File | Command | Expected result |
| --- | --- | --- |
| protected-table.json | `python -m extension1 examples/protected-table.json --format text` | The table was present before the decision. AWS denied DeleteTable at 09:01 UTC. A separate read found the table present at 09:02 UTC. |
| pilot.json | `python -m extension1.pilot examples/pilot.json` | Ten labelled results match; a mismatched expected outcome makes the command exit with status 1. |

A case has a target, events, an observation and an as-of time. The optional baseline must be at or before the decision. The target names a single receipt, account, region, table and operation. Keep retry attempts inside that run's time window. For a review with verified receipts, the signed decision supplies the target and approval information.

The protected-table fixture demonstrates an AWS denial. A specific resource policy can only be attributed when separate evidence identifies it. Disagreement between the event and observation warrants investigation; neither a later read nor a process exit code establishes the entire plan's outcome.
