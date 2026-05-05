import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.brave_search import BraveRateLimiter, BraveSearchClient


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self.payload


class RecordingSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "params": dict(params or {}), "timeout": timeout})
        return self.response


class TestBraveSearch(unittest.TestCase):
    def test_llm_context_uses_subscription_header_without_returning_secret(self):
        session = RecordingSession(
            FakeResponse(
                {
                    "grounding": {
                        "chunks": [
                            {"text": "Ouroboros 11D learning context from Brave."},
                            {"text": "Gemma4 can distill this into compact training memories."},
                        ]
                    },
                    "sources": {"https://example.com/ai": {"title": "AI source"}},
                },
                headers={"X-RateLimit-Limit": "50, 100000"},
            )
        )
        client = BraveSearchClient(
            api_key="brave-secret-123456",
            session=session,
            limiter=BraveRateLimiter(50),
        )

        result = client.llm_context("Ouroboros 11D pockets", maximum_number_of_urls=3)

        self.assertEqual(result["status"], "success")
        self.assertIn("Ouroboros 11D learning context", result["document"])
        self.assertEqual(result["source_urls"], ["https://example.com/ai"])
        self.assertEqual(session.calls[0]["headers"]["X-Subscription-Token"], "brave-secret-123456")
        self.assertNotIn("brave-secret-123456", str(result))
        self.assertEqual(session.calls[0]["params"]["maximum_number_of_urls"], 3)

    def test_status_reads_brave_key_from_environment(self):
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "brave-secret-abcdef"}, clear=False):
            status = BraveSearchClient(session=RecordingSession(FakeResponse({}))).status()

        self.assertEqual(status["status"], "configured")
        self.assertTrue(status["configured"])
        self.assertNotIn("brave-secret-abcdef", str(status))


if __name__ == "__main__":
    unittest.main()
