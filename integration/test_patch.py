"""Run with the patched ActionLock package and upstream test fixtures on PYTHONPATH."""
import tempfile
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from actionlock.approvals import ApprovalStore, binding_for
from actionlock.contract import Contract, load_signed_contract, sign_contract
from actionlock.inventory import Inventory
from actionlock.plan import parse_plan
from actionlock.receipts import ReceiptLog
from actionlock.schema import ValidationError
from actionlock.verifier import verify
from fixtures import NOW, contract_dict, inventory_dict, resource, signer
from plan_builder import change, plan


class ExtensionIntegration(unittest.TestCase):
    def test_ten_paired_tag_scopes(self):
        addr = "aws_s3_bucket.scratch_1"
        inv = Inventory.from_dict(inventory_dict(resource(addr, "aws_s3_bucket", "staging", False)))
        for key in ("Owner", "CostCenter", "Team", "Project", "Service", "Department", "Contact", "Billing", "Subsystem", "Release"):
            with self.subTest(key=key):
                before = {"bucket": "scratch-one", "tags": {"Environment":"staging", key:"old"}}
                after = {**before, "tags": {**before["tags"], key:"new"}}
                p = parse_plan(plan(change(addr, "aws_s3_bucket", ["update"], before, after)))
                for allowed, expected in [(key, "inside"), ("DifferentTag", "outside")]:
                    contract = Contract.from_dict(contract_dict(allowed_changes=["update"], allowed_tag_keys=[allowed]))
                    self.assertEqual(verify(contract, p, inv).outcome, expected)

    def test_extra_attribute_unknown_and_signature(self):
        addr = "aws_s3_bucket.scratch_1"
        inv = Inventory.from_dict(inventory_dict(resource(addr, "aws_s3_bucket", "staging", False)))
        c = Contract.from_dict(contract_dict(allowed_changes=["update"], allowed_tag_keys=["Owner"]))
        envelope = sign_contract(c, signer())
        self.assertEqual(load_signed_contract(envelope, signer(), NOW), c)
        envelope["contract"]["allowed_tag_keys"] = ["Different"]
        with self.assertRaises(ValidationError):
            load_signed_contract(envelope, signer(), NOW)
        before = {"bucket":"scratch-one", "tags":{"Environment":"staging","Owner":"a"}}
        after = {**before, "tags":{**before["tags"], "Owner":"b"}}
        for new, unknown in [(dict(after, force_destroy=True), {}), (after, {"tags_all": True}), (after, True)]:
            p = parse_plan(plan(change(addr, "aws_s3_bucket", ["update"], before, new, after_unknown=unknown)))
            self.assertEqual(verify(c, p, inv).outcome, "outside")

    def test_outbox_rollback_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            c = Contract.from_dict(contract_dict())
            store = ApprovalStore(path / "approvals.db")
            self.addCleanup(store.close)
            verdict = {"contract_id":c.contract_id, "outcome":"inside", "aws_account_id":c.aws_account_id,
                       "region":c.region, "terraform_version":"1.9.0"}
            binding = binding_for(verdict, "a"*64, c.workspace, "b"*64, c)
            req = store.create(verdict, binding, c, NOW)
            store.connection.execute("CREATE TRIGGER reject BEFORE INSERT ON decision_outbox BEGIN SELECT RAISE(ABORT,'failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                store.consume(req, binding, NOW, "al-test", {"request_id": req})
            self.assertEqual(store.receipt_ids(), [])
            store.connection.execute("DROP TRIGGER reject")
            store.consume(req, binding, NOW, "al-test", {"request_id": req})
            log = ReceiptLog(path/"receipts.jsonl", signer())
            with patch.object(log, "append", side_effect=OSError):
                with self.assertRaises(OSError):
                    store.export_pending(log)
            # Simulate the other crash boundary: append reached disk before export acknowledgement.
            log.append("decision", {"request_id": req, "approvers":[]}, NOW, "al-test")
            store.export_pending(log)
            store.export_pending(log)
            self.assertEqual(log.verify(), 1)
            with self.assertRaises(ValidationError):
                store.consume(req, binding, NOW, "al-other")

    def test_signed_runner_decision_to_evidence(self):
        import json
        from actionlock.runner import Runner, lock_file_digest
        from actionlock.approvals import ApproverDirectory
        from actionlock.plan import plan_file_digest
        from test_runner import FakeTerraform, FakeSts, ROLE, TOKENS
        from extension1.receipts import decision_target
        from extension1.evidence import review
        from fixtures import STAGING_ACCOUNT
        addr = "aws_dynamodb_table.cache_copy"
        table = "staging-orders"
        inv = Inventory.from_dict(inventory_dict(resource(addr, "aws_dynamodb_table", "staging", True)))
        doc = plan(change(addr, "aws_dynamodb_table", ["delete"], {"name": table}, None))
        c = Contract.from_dict(contract_dict())
        verdict = verify(c, parse_plan(doc), inv).to_dict()
        self.assertEqual(verdict["outcome"], "outside")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            saved = path / "plan"
            saved.write_bytes(b"offline fixture")
            (path / ".terraform.lock.hcl").write_text("fixture")
            store = ApprovalStore(path / "requests.db")
            self.addCleanup(store.close)
            binding = binding_for(verdict, plan_file_digest(saved), c.workspace, lock_file_digest(path), c)
            request = store.create(verdict, binding, c, NOW)
            for user, token in TOKENS.items():
                store.approve(request, user, token, ApproverDirectory(TOKENS), NOW)
            receipts = ReceiptLog(path / "receipts.jsonl", signer())
            runner = Runner(signer(), store, receipts, FakeSts(), FakeTerraform(doc, exit_code=1),
                            lambda _: inv, {STAGING_ACCOUNT: ROLE}, lambda: NOW)
            run = runner.run(request, sign_contract(c, signer()), path, saved)
            self.assertFalse(run.applied)
            with patch("actionlock.contract.HmacSigner.from_environment", return_value=signer()):
                target, approval = decision_target(receipts.path, run.receipt_id, addr)
            self.assertEqual(set(approval["approvers"]), set(TOKENS))
            self.assertEqual(approval["runner_result"]["status"], "apply_failed_possibly_partial")
            sample = json.loads((Path(__file__).resolve().parents[1]/"examples/protected-table.json").read_text())
            event = sample["events"][0]
            event["awsRegion"] = sample["observation"]["region"] = c.region
            event["userIdentity"]["sessionContext"]["sourceIdentity"] = run.receipt_id
            result = review(target, [event], sample["observation"], as_of=sample["as_of"])
            self.assertEqual(result["outcome"], "denial_and_opposite_state_observed")
