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
