import contextlib
import io
import json
import sys
import unittest
from unittest.mock import Mock, patch
from types import ModuleType

from extension1.__main__ import main
from test_review_cli import EXAMPLE


class CollectionCliTests(unittest.TestCase):
    def setUp(self):
        self.sdk = Mock()
        self.clients = {name: Mock() for name in ("sts", "cloudtrail", "dynamodb")}
        self.sdk.Session.return_value.client.side_effect = self.clients.__getitem__
        case = json.loads(EXAMPLE.read_text())
        self.clients["sts"].get_caller_identity.return_value = {"Account": case["target"]["account"]}
        self.clients["cloudtrail"].get_paginator.return_value.paginate.return_value = [
            {"Events": [{"CloudTrailEvent": json.dumps(case["events"][0])}]}]
        self.clients["dynamodb"].describe_table.return_value = {"Table": {
            "TableArn": "arn:aws:dynamodb:eu-west-1:111111111111:table/staging-orders", "TableStatus": "ACTIVE"}}

    def run_cli(self, *args):
        from datetime import datetime, timezone
        stdout = io.StringIO()
        exceptions = ModuleType("botocore.exceptions")
        exceptions.ClientError = type("ClientError", (Exception,), {})
        exceptions.BotoCoreError = type("BotoCoreError", (Exception,), {})
        modules = {"boto3": self.sdk, "botocore": ModuleType("botocore"), "botocore.exceptions": exceptions}
        with patch.dict(sys.modules, modules), patch.object(sys, "argv", ["review", str(EXAMPLE), *args]), \
                patch("extension1.__main__.datetime") as clock, patch("extension1.__main__.observe_table") as observe, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            from extension1.evidence import observe_table
            instant = datetime(2026, 11, 14, 9, 5, tzinfo=timezone.utc)
            clock.now.return_value = instant
            observe.side_effect = lambda client, target: observe_table(client, target, lambda: instant)
            main()
        return json.loads(stdout.getvalue())

    def test_scoped_lookup_and_new_observation(self):
        report = self.run_cli("--lookup-events", "--observe")
        self.assertEqual(report["aws_attempt"], "denied")
        self.assertEqual(report["outcome"], "denial_and_opposite_state_observed")
        self.clients["dynamodb"].describe_table.assert_called_once()

    def test_wrong_account_stops_collection(self):
        self.clients["sts"].get_caller_identity.return_value = {"Account": "222222222222"}
        with self.assertRaises(SystemExit) as error:
            self.run_cli("--snapshot")
        self.assertEqual(error.exception.code, 2)
        self.clients["dynamodb"].describe_table.assert_not_called()

    def test_snapshot_can_be_stored_for_later_review(self):
        row = self.run_cli("--snapshot")
        self.assertEqual(row["state"], "present")
        self.assertEqual(row["table"], "staging-orders")
        self.clients["cloudtrail"].get_paginator.assert_not_called()
