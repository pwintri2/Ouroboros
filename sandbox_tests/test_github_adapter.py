import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.api_key_store import save_provider_api_key
from controller.github_adapter import GitHubAdapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestGitHubAdapter(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="github-adapter-")
        self.env = patch.dict(
            os.environ,
            {
                "WINTRIP_API_KEY_STORE": str(Path(self.tempdir.name) / "keys.json"),
                "GITHUB_TOKEN": "",
                "GH_TOKEN": "",
                "GITHUB_API_TOKEN": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tempdir.cleanup()

    def test_status_uses_api_key_store_without_returning_token(self):
        save_provider_api_key("github", "ghp_testsecret123456789")

        status = GitHubAdapter().status()

        self.assertEqual(status["status"], "configured")
        self.assertTrue(status["token"]["configured"])
        self.assertEqual(status["token"]["source"], "api_key_store")
        self.assertFalse(status["token"]["secrets_returned"])
        self.assertNotIn("ghp_testsecret123456789", json.dumps(status))

    def test_public_repo_request_does_not_send_token_without_private_approval(self):
        seen_headers = {}

        def fake_urlopen(request, timeout=0):
            seen_headers.update(dict(request.header_items()))
            return FakeResponse(
                {
                    "id": 1,
                    "name": "Hello-World",
                    "full_name": "octocat/Hello-World",
                    "private": False,
                    "html_url": "https://github.com/octocat/Hello-World",
                    "description": "public repo",
                    "owner": {"login": "octocat", "type": "User", "html_url": "https://github.com/octocat"},
                }
            )

        adapter = GitHubAdapter(token="ghp_should_not_be_sent_for_public")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = adapter.get_repository("octocat/Hello-World")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["repo"]["full_name"], "octocat/Hello-World")
        self.assertFalse(result["repo"]["private"])
        self.assertNotIn("Authorization", seen_headers)
        self.assertNotIn("ghp_should_not_be_sent_for_public", json.dumps(result))

    def test_private_repo_metadata_blocks_without_approval_and_redacts(self):
        def fake_urlopen(request, timeout=0):
            return FakeResponse(
                {
                    "id": 2,
                    "name": "secret",
                    "full_name": "me/secret",
                    "private": True,
                    "description": "token=SUPERSECRET",
                    "owner": {"login": "me", "type": "User"},
                }
            )

        adapter = GitHubAdapter(token="ghp_private_token")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            blocked = adapter.get_repository("me/secret")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            approved = adapter.get_repository("me/secret", approval="Akkoord")

        self.assertEqual(blocked["status"], "blocked")
        self.assertTrue(blocked["approval_required"])
        self.assertFalse(blocked["secrets_returned"])
        self.assertNotIn("SUPERSECRET", json.dumps(blocked))
        self.assertEqual(approved["status"], "success")
        self.assertTrue(approved["private"])
        self.assertNotIn("SUPERSECRET", json.dumps(approved))
        self.assertNotIn("ghp_private_token", json.dumps(approved))

    def test_search_forces_public_scope_and_filters_private_items(self):
        seen_urls = []

        def fake_urlopen(request, timeout=0):
            seen_urls.append(request.full_url)
            return FakeResponse(
                {
                    "total_count": 2,
                    "items": [
                        {"id": 1, "full_name": "public/repo", "name": "repo", "private": False, "owner": {"login": "public"}},
                        {"id": 2, "full_name": "private/repo", "name": "repo", "private": True, "owner": {"login": "private"}},
                    ],
                }
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = GitHubAdapter(token="ghp_search_token").search_repositories("ouroboros", limit=5)

        self.assertEqual(result["status"], "success")
        self.assertIn("is%3Apublic", seen_urls[0])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["private_items_filtered"], 1)
        self.assertFalse(result["items"][0]["private"])
        self.assertNotIn("ghp_search_token", json.dumps(result))

    def test_private_search_is_preview_blocked_without_network_call(self):
        with patch("urllib.request.urlopen") as urlopen:
            result = GitHubAdapter(token="ghp_secret").search_repositories("private repo is:private", limit=5)

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        urlopen.assert_not_called()
        self.assertNotIn("ghp_secret", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
