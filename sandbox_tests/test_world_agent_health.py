import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import APIRouter  # noqa: F401
except ModuleNotFoundError as exc:
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""


@unittest.skipIf(MISSING_FASTAPI, MISSING_FASTAPI)
class TestWorldAgentHealth(unittest.TestCase):
    def test_world_dependencies_payload_shape(self):
        from controller.api.world_agent_routes import _world_dependencies

        payload = _world_dependencies()
        for key in ("status", "memory_available", "chromadb", "playwright", "host_bridge", "fake_success"):
            self.assertIn(key, payload, msg=f"missing {key} in dependencies payload")
        self.assertEqual(payload["fake_success"], False)
        self.assertIn(payload["status"], {"online", "degraded"})

    def test_world_health_payload_shape(self):
        from controller.api.world_agent_routes import _world_health

        payload = _world_health()
        for key in ("status", "memory", "bridge", "browser_automation", "recent_actions_count", "fake_success"):
            self.assertIn(key, payload, msg=f"missing {key} in health payload")
        self.assertEqual(payload["fake_success"], False)
        # Status must be a real ladder term — not raw promotion of file presence.
        self.assertIn(payload["status"], {"online", "degraded", "unavailable", "missing", "error"})


if __name__ == "__main__":
    unittest.main()
