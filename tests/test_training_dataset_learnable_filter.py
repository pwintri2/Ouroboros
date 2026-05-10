import unittest

from controller import training_dataset_builder as builder


class FakeCollection:
    def get(self, limit=1000, include=None):
        return {
            "documents": ["good", "audit", "not-learnable", "pending", "legacy-missing-flags"],
            "metadatas": [
                {"approval_status": "approved", "learnable": True, "audit_only": False, "content_hash": "1"},
                {"approval_status": "approved", "learnable": True, "audit_only": True, "content_hash": "2"},
                {"approval_status": "approved", "learnable": False, "audit_only": False, "content_hash": "3"},
                {"approval_status": "pending_philip_akkoord", "learnable": True, "audit_only": False, "content_hash": "4"},
                {"approval_status": "approved", "content_hash": "5"},
            ],
        }


class TestTrainingDatasetLearnableFilter(unittest.TestCase):
    def test_get_approved_records_requires_approved_learnable_non_audit(self):
        original = builder.get_training_collection
        builder.get_training_collection = lambda: FakeCollection()
        try:
            records = builder.get_approved_records(limit=100)
        finally:
            builder.get_training_collection = original

        self.assertEqual([record["document"] for record in records], ["good"])
        self.assertTrue(records[0]["metadata"]["learnable"])
        self.assertFalse(records[0]["metadata"]["audit_only"])


if __name__ == "__main__":
    unittest.main()
