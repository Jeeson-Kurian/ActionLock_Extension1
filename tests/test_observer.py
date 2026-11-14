import json
from unittest import TestCase
from unittest.mock import Mock
from test_review_cli import EXAMPLE
from extension1.evidence import observe_table


class ObservationTests(TestCase):
    def setUp(self):
        self.target = json.loads(EXAMPLE.read_text())["target"]
        self.arn = "arn:aws:dynamodb:eu-west-1:111111111111:table/staging-orders"

    def read(self, arn, status):
        client = Mock()
        client.describe_table.return_value = {"Table": {"TableArn": arn, "TableStatus": status}}
        return observe_table(client, self.target)["state"]

    def test_read_requires_matching_resource_identity(self):
        self.assertEqual(self.read(self.arn.replace("eu-west-1", "eu-west-2"), "ACTIVE"), "unknown")

    def test_pending_deletion_is_transitional(self):
        self.assertEqual(self.read(self.arn, "DELETING"), "transitioning")

    def test_identified_active_table_is_present(self):
        self.assertEqual(self.read(self.arn, "ACTIVE"), "present")
