import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

from extension1.cloudtrail import IncompleteHistory, lookup_events
from extension1.evidence import check_baseline

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/protected-table.json"


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(EXAMPLE.read_text())
        self.client = Mock()

    def lookup(self, pages, limit=20):
        self.client.get_paginator.return_value.paginate.return_value = pages
        return lookup_events(self.client, self.case["target"], self.case["as_of"], page_limit=limit)

    def test_collects_every_page(self):
        event = self.case["events"][0]
        self.assertEqual(self.lookup([{"Events": [], "NextToken": "more"},
                                      {"Events": [{"CloudTrailEvent": json.dumps(event)}]}]), [event])
        params = self.client.get_paginator.return_value.paginate.call_args.kwargs
        self.assertEqual(params["LookupAttributes"][0]["AttributeValue"], "DeleteTable")

    def test_partial_page_window_is_explicit(self):
        with self.assertRaises(IncompleteHistory):
            self.lookup([{"Events": [], "NextToken": "more"}], limit=1)

    def test_missing_page_data(self):
        with self.assertRaises(IncompleteHistory):
            self.lookup([{}])

    def test_baseline_time_and_target(self):
        before = dict(self.case["observation"], observed_at="2026-11-14T08:59:00Z")
        self.assertEqual(check_baseline(self.case["target"], before), before)
        for bad in (dict(before, table="other"), self.case["observation"]):
            with self.assertRaises(ValueError):
                check_baseline(self.case["target"], bad)

    def test_text_and_json_agree(self):
        command = [sys.executable, "-m", "extension1", str(EXAMPLE)]
        result = json.loads(subprocess.check_output(command, cwd=ROOT))
        rendered = subprocess.check_output(command + ["--format", "text"], cwd=ROOT, text=True)
        for phrase in ("AWS attempt: denied", "Independent read: present", result["outcome"]):
            self.assertIn(phrase, rendered)
