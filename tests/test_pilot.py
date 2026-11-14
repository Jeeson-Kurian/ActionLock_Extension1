import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from extension1.pilot import replay

ROOT = Path(__file__).resolve().parents[1]


class PilotTests(unittest.TestCase):
    def test_all_supplied_cases_match(self):
        cases = json.loads((ROOT / "examples/pilot.json").read_text())
        results = list(replay(cases))
        self.assertEqual(len(results), 10)
        for result in results:
            with self.subTest(case=result["case"]):
                self.assertEqual(result["actual"], result["expected"])

    def test_mismatch_is_reported_and_fails_the_process(self):
        cases = json.loads((ROOT / "examples/pilot.json").read_text())[:1]
        cases[0]["expected"]["outcome"] = "pending"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mismatch.json"
            path.write_text(json.dumps(cases))
            run = subprocess.run([sys.executable, "-m", "extension1.pilot", str(path)], cwd=ROOT,
                                 capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)["passed"], 0)
