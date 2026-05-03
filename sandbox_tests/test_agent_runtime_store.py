import json
import tempfile
import unittest
from pathlib import Path

from controller.agent_runtime.events import EventLog, append_event, read_events
from controller.agent_runtime.models import JobRecord, new_job_id
from controller.agent_runtime.store import JobStore


class TestJobStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agent-runtime-store-")
        self.addCleanup(self.tmp.cleanup)
        self.store = JobStore(
            runtime_root=Path(self.tmp.name) / "store",
            artifact_root=Path(self.tmp.name) / "out",
        )

    def _build(self, agent: str = "codex", task: str = "do work") -> JobRecord:
        job_id = new_job_id(agent)
        return JobRecord(job_id=job_id, agent=agent, task=task)

    def test_upsert_persists_record_to_jobs_json(self):
        record = self._build()
        self.store.upsert(record)

        payload = json.loads(self.store.jobs_path.read_text(encoding="utf-8"))
        self.assertIn(record.job_id, payload["jobs"])
        self.assertEqual(payload["jobs"][record.job_id]["task"], "do work")
        self.assertIsNotNone(payload["last_updated"])

    def test_list_jobs_filters_by_agent_and_sorts_newest_first(self):
        first = self._build("codex", "earlier")
        first.created_at = "2026-05-03T10:00:00Z"
        self.store.upsert(first)
        second = self._build("codex", "later")
        second.created_at = "2026-05-03T11:00:00Z"
        self.store.upsert(second)
        other = self._build("claude", "irrelevant")
        self.store.upsert(other)

        codex_only = self.store.list_jobs(agent="codex")
        self.assertEqual([job["job_id"] for job in codex_only], [second.job_id, first.job_id])
        all_jobs = self.store.list_jobs()
        self.assertEqual({job["agent"] for job in all_jobs}, {"codex", "claude"})

    def test_update_merges_changes_and_returns_record(self):
        record = self._build()
        self.store.upsert(record)

        updated = self.store.update(record.job_id, {"status": "completed", "exit_code": 0})
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["exit_code"], 0)
        self.assertNotEqual(updated["updated_at"], record.updated_at)

    def test_update_unknown_job_returns_none(self):
        self.assertIsNone(self.store.update("does-not-exist", {"status": "completed"}))

    def test_corrupted_jobs_file_does_not_crash_load(self):
        self.store.jobs_path.write_text("{not json", encoding="utf-8")

        record = self._build()
        self.store.upsert(record)
        self.assertEqual(self.store.list_jobs()[0]["job_id"], record.job_id)


class TestEventLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agent-runtime-events-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "events.jsonl"

    def test_append_event_creates_jsonl_with_ts_and_payload(self):
        append_event(self.path, "started", {"pid": 42})
        append_event(self.path, "progress", {"chunk": "hi"})

        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first["type"], "started")
        self.assertEqual(first["data"]["pid"], 42)
        self.assertIn("ts", first)

    def test_read_events_supports_after_index_paging(self):
        for index in range(5):
            append_event(self.path, "tick", {"i": index})

        all_events = read_events(self.path, after_index=0, limit=10)
        page = read_events(self.path, after_index=3, limit=10)
        self.assertEqual(len(all_events), 5)
        self.assertEqual([event["data"]["i"] for event in page], [3, 4])
        self.assertEqual(page[0]["index"], 3)

    def test_read_events_skips_corrupted_lines(self):
        append_event(self.path, "ok", {"i": 0})
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("not-json\n")
        append_event(self.path, "ok", {"i": 1})

        events = read_events(self.path)
        self.assertEqual([event["data"]["i"] for event in events], [0, 1])

    def test_event_log_wrapper_appends_and_reads(self):
        log = EventLog(self.path)
        log.append("hello", {"x": 1})
        events = log.read()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"], {"x": 1})


if __name__ == "__main__":
    unittest.main()
