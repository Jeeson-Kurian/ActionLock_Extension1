import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from extension1.evidence import observe_table, review


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads((Path(__file__).resolve().parents[1] / "examples/protected-table.json").read_text())
        self.event = self.case["events"][0]

    def report(self):
        c = self.case
        return review(c["target"], c["events"], c["observation"], as_of=c["as_of"])

    def test_deny_and_state(self):
        self.assertEqual(self.report()["outcome"], "denial_and_opposite_state_observed")
        self.assertEqual(self.report()["aws_attempt"], "denied")
        self.case["observation"]["state"] = "absent"
        self.assertEqual(self.report()["outcome"], "conflicting_evidence")

    def test_accepted_delete_and_transition(self):
        del self.event["errorCode"]
        self.case["observation"]["state"] = "transitioning"
        self.assertEqual(self.report()["outcome"], "pending")
        self.case["observation"]["state"] = "absent"
        self.assertEqual(self.report()["outcome"], "expected_state_observed")

    def test_delayed_and_stale_evidence(self):
        self.case["observation"]["observed_at"] = self.event["eventTime"]
        self.assertEqual(self.report()["outcome"], "pending")
        self.case["events"] = []
        self.assertEqual(self.report()["aws_attempt"], "pending")

    def test_scope(self):
        for field in ("awsRegion", "recipientAccountId", "eventName", "eventSource"):
            with self.subTest(field=field):
                event = dict(self.event, **{field: "other"})
                self.case["events"] = [event]
                self.assertEqual(self.report()["aws_attempt"], "pending")
        self.event["userIdentity"]["sessionContext"]["sourceIdentity"] = "al-other"
        self.case["events"] = [self.event]
        self.assertEqual(self.report()["aws_attempt"], "pending")

    def test_duplicate_and_mixed(self):
        self.case["events"].append(copy.deepcopy(self.event))
        self.assertEqual(len(self.report()["events"]), 1)
        self.case["events"][1].pop("errorCode")
        with self.assertRaises(ValueError):
            self.report()
        self.case["events"][1]["eventID"] = "other"
        self.assertEqual(self.report()["outcome"], "pending")
        self.assertEqual(self.report()["aws_attempt"], "mixed")

    def test_failed_read(self):
        class AwsError(Exception):
            pass
        for code, expected in [("ResourceNotFoundException", "absent"), ("AccessDeniedException", "unreadable"),
                               ("ThrottlingException", "unknown")]:
            error = AwsError()
            error.response = {"Error": {"Code": code}}
            client = Mock()
            client.describe_table.side_effect = error
            self.assertEqual(observe_table(client, self.case["target"])["state"], expected)
            client.describe_table.assert_called_once_with(TableName="staging-orders")

    def test_sanitised_events_and_failed_attempts(self):
        self.event["errorMessage"] = "customer-sensitive-material"
        self.event["errorCode"] = "ThrottlingException"
        self.assertEqual(self.report()["aws_attempt"], "failed")
        self.assertNotIn("customer-sensitive-material", json.dumps(self.report()))

    def test_unrelated_read(self):
        self.case["observation"]["table"] = "wrong"
        with self.assertRaises(ValueError):
            self.report()

    def test_create(self):
        self.case["target"]["operation"] = self.event["eventName"] = "CreateTable"
        del self.event["errorCode"]
        self.assertEqual(self.report()["outcome"], "expected_state_observed")
