import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.chroma_sync_adapter import (
    ChromaSyncAdapter,
    ChromaSyncConfig,
    _diff_payloads,
    _export_from_client,
    _import_into_client,
)
from controller.vps_deploy_adapter import VPSProfile


class FakeCollection:
    def __init__(self, records=None):
        self.records = {}
        for record in records or []:
            self.records[record["id"]] = dict(record)

    def count(self):
        return len(self.records)

    def get(self, ids=None, limit=100, offset=0, include=None):
        rows = list(self.records.items())
        if ids is not None:
            rows = [(item_id, self.records[item_id]) for item_id in ids if item_id in self.records]
        else:
            rows = rows[offset : offset + limit]
        return {
            "ids": [item_id for item_id, _record in rows],
            "documents": [record.get("document", "") for _item_id, record in rows],
            "metadatas": [dict(record.get("metadata", {})) for _item_id, record in rows],
            "embeddings": [record.get("embedding", [0.1, 0.2]) for _item_id, record in rows],
        }

    def add(self, ids, documents, metadatas, embeddings=None):
        for index, item_id in enumerate(ids):
            if item_id in self.records:
                raise RuntimeError("duplicate id")
            self.records[item_id] = {
                "id": item_id,
                "document": documents[index],
                "metadata": dict(metadatas[index]),
                "embedding": (embeddings[index] if embeddings else [0.1, 0.2]),
            }


class FakeClient:
    def __init__(self):
        self.collections = {}

    def get_collection(self, name):
        if name not in self.collections:
            raise RuntimeError("missing")
        return self.collections[name]

    def get_or_create_collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


class TestChromaSyncAdapter(unittest.TestCase):
    def test_export_diff_and_import_deduplicate_by_content_hash(self):
        local = FakeClient()
        remote = FakeClient()
        local.collections["wintrip_knowledge"] = FakeCollection(
            [
                {
                    "id": "local-a",
                    "document": "same",
                    "metadata": {"content_hash": "hash-a"},
                    "embedding": [0.1, 0.2],
                }
            ]
        )
        remote.collections["wintrip_knowledge"] = FakeCollection(
            [
                {
                    "id": "remote-a",
                    "document": "same remote",
                    "metadata": {"content_hash": "hash-a"},
                    "embedding": [0.3, 0.4],
                },
                {
                    "id": "remote-b",
                    "document": "new remote",
                    "metadata": {"content_hash": "hash-b"},
                    "embedding": [0.5, 0.6],
                },
            ]
        )

        local_preview = _export_from_client(local, ["wintrip_knowledge"], include_documents=False, max_records_per_collection=100, origin="local")
        remote_preview = _export_from_client(remote, ["wintrip_knowledge"], include_documents=False, max_records_per_collection=100, origin="vps")
        diff = _diff_payloads(local_preview, remote_preview)

        self.assertEqual(diff["collections"]["wintrip_knowledge"]["missing_on_local"], 1)
        self.assertEqual(diff["collections"]["wintrip_knowledge"]["missing_on_remote"], 0)

        remote_full = _export_from_client(remote, ["wintrip_knowledge"], include_documents=True, max_records_per_collection=100, origin="vps")
        imported = _import_into_client(local, remote_full, source_label="vps")

        self.assertEqual(imported["status"], "success")
        self.assertEqual(imported["collections"]["wintrip_knowledge"]["imported"], 1)
        self.assertEqual(local.collections["wintrip_knowledge"].count(), 2)
        self.assertIn("remote-b", local.collections["wintrip_knowledge"].records)

    def test_execute_blocks_without_akkoord_before_remote_access(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(cmd)
            raise AssertionError("runner should not be called without Akkoord")

        with tempfile.TemporaryDirectory(prefix="chroma-sync-") as tmp:
            Path(tmp, ".secrets").mkdir()
            adapter = ChromaSyncAdapter(
                profile=VPSProfile(ssh_host_alias="vps", user="deploy", port=22),
                workspace=tmp,
                ssh_binary="/usr/bin/ssh",
                runner=fake_runner,
                config=ChromaSyncConfig(
                    collections=("wintrip_knowledge",),
                    remote_workspace="/var/www/philip-wintrip.nl/html/Ouroboros",
                    remote_chroma_path="/var/www/philip-wintrip.nl/html/Ouroboros/wintrip_brain",
                ),
            )

            result = adapter.execute(approval="akkoord", prefer_bridge=False)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
