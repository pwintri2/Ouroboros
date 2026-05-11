"""Tests for controller.subscription_store — AI subscription management."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class TestSubscriptionStoreBasics(unittest.TestCase):
    """Test the subscription store CRUD operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "test_subscriptions.json")
        self.env_patcher = patch.dict(os.environ, {"WINTRIP_SUBSCRIPTION_STORE": self.store_path})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        try:
            os.unlink(self.store_path)
        except FileNotFoundError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except Exception:
            pass

    def test_import(self):
        from controller.subscription_store import (
            SUBSCRIPTION_PROVIDERS,
            activate_subscription,
            delete_subscription,
            load_subscriptions,
            normalize_subscription_provider,
            save_subscription,
            subscription_api_key_for_provider,
            subscription_credential_for_provider,
            subscription_status,
            subscription_store_path,
            validate_subscription,
        )
        self.assertTrue(len(SUBSCRIPTION_PROVIDERS) >= 5)

    def test_store_path(self):
        from controller.subscription_store import subscription_store_path

        path = subscription_store_path()
        self.assertEqual(str(path), self.store_path)

    def test_default_store_path_prefers_current_workspace_over_host_workspace_mount(self):
        from controller.subscription_store import subscription_store_path

        previous = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="subscription-cwd-") as tmp:
            with patch.dict(
                os.environ,
                {
                    "WINTRIP_SUBSCRIPTION_STORE": "",
                    "OUROBOROS_SUBSCRIPTION_STORE": "",
                    "WINTRIP_WORKSPACE": "",
                    "WORKSPACE_ROOT": "",
                    "WINTRIP_PROJECT_ROOT": "",
                },
                clear=False,
            ):
                os.chdir(tmp)
                try:
                    expected = Path(tmp, ".secrets", "ouroboros_subscriptions.json").resolve()
                    self.assertEqual(subscription_store_path(), expected)
                finally:
                    os.chdir(previous)

    def test_normalize_provider(self):
        from controller.subscription_store import normalize_subscription_provider

        self.assertEqual(normalize_subscription_provider("openai"), "openai")
        self.assertEqual(normalize_subscription_provider("chatgpt"), "openai")
        self.assertEqual(normalize_subscription_provider("chatgpt-plus"), "openai")
        self.assertEqual(normalize_subscription_provider("claude"), "anthropic")
        self.assertEqual(normalize_subscription_provider("claude-pro"), "anthropic")
        self.assertEqual(normalize_subscription_provider("gemini"), "google")
        self.assertEqual(normalize_subscription_provider("gemini-advanced"), "google")
        self.assertEqual(normalize_subscription_provider("deepseek"), "deepseek")
        self.assertEqual(normalize_subscription_provider("deepseek-chat"), "deepseek")
        self.assertEqual(normalize_subscription_provider("deekseek"), "deepseek")
        self.assertEqual(normalize_subscription_provider("grok"), "xai")

        with self.assertRaises(ValueError):
            normalize_subscription_provider("nonexistent")

    def test_empty_subscriptions(self):
        from controller.subscription_store import load_subscriptions, subscription_status

        subs = load_subscriptions()
        self.assertIsInstance(subs, dict)
        self.assertEqual(len(subs), 0)

        status = subscription_status()
        self.assertIsInstance(status, dict)
        self.assertTrue(len(status) >= 5)
        for provider_id, details in status.items():
            self.assertEqual(details["status"], "inactive")
            self.assertFalse(details["active"])

    def test_save_subscription_api_key(self):
        from controller.subscription_store import (
            load_subscriptions,
            save_subscription,
            subscription_status,
        )

        result = save_subscription(
            "openai",
            auth_mode="api_key_from_subscription",
            api_key="sk-test-12345678901234567890",
            plan_label="ChatGPT Plus",
        )
        self.assertEqual(result["provider"], "openai")
        self.assertIn(result["status"], ("active", "configured"))
        self.assertTrue(result["active"])
        self.assertTrue(result["has_credential"])
        self.assertTrue(result["api_key_ready"])
        self.assertEqual(result["plan_label"], "ChatGPT Plus")

        subs = load_subscriptions()
        self.assertIn("openai", subs)
        self.assertEqual(subs["openai"]["api_key"], "sk-test-12345678901234567890")

        status = subscription_status()
        self.assertIn(status["openai"]["status"], ("active", "configured"))

    def test_save_deepseek_api_key_subscription(self):
        from controller.subscription_store import (
            save_subscription,
            subscription_api_key_for_provider,
            subscription_status,
        )

        result = save_subscription(
            "deepseek-chat",
            auth_mode="api_key_from_subscription",
            api_key="sk-deepseek-test-1234567890",
            plan_label="DeepSeek API",
        )

        self.assertEqual(result["provider"], "deepseek")
        self.assertTrue(result["api_key_ready"])
        self.assertIn("deepseek-v4-flash", result["models"])
        self.assertEqual(result["api_key_url"], "https://platform.deepseek.com/api_keys")
        self.assertEqual(subscription_api_key_for_provider("deepseek"), "sk-deepseek-test-1234567890")
        self.assertNotIn("sk-deepseek-test-1234567890", json.dumps(subscription_status()))

    def test_save_subscription_session_token(self):
        from controller.subscription_store import save_subscription

        result = save_subscription(
            "anthropic",
            auth_mode="session_token",
            session_token="sess-abcdefghijklmnop1234567890",
            plan_label="Claude Pro",
        )
        self.assertEqual(result["provider"], "anthropic")
        self.assertTrue(result["active"])
        self.assertTrue(result["has_credential"])
        self.assertFalse(result["api_key_ready"])

    def test_save_subscription_invalid_auth_mode(self):
        from controller.subscription_store import save_subscription

        with self.assertRaises(ValueError):
            save_subscription("openai", auth_mode="nonexistent_mode")

    def test_delete_subscription(self):
        from controller.subscription_store import (
            delete_subscription,
            load_subscriptions,
            save_subscription,
        )

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-test-12345678901234567890")
        self.assertIn("openai", load_subscriptions())

        result = delete_subscription("openai")
        self.assertEqual(result["provider"], "openai")
        self.assertFalse(result["active"])
        self.assertNotIn("openai", load_subscriptions())

    def test_activate_deactivate(self):
        from controller.subscription_store import (
            activate_subscription,
            save_subscription,
        )

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-test-12345678901234567890")

        result = activate_subscription("openai", False)
        self.assertFalse(result["active"])

        result = activate_subscription("openai", True)
        self.assertTrue(result["active"])

    def test_validate_api_key(self):
        from controller.subscription_store import (
            save_subscription,
            validate_subscription,
        )

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-test-12345678901234567890")
        result = validate_subscription("openai")
        self.assertEqual(result["validation_status"], "valid")

    def test_validate_missing_credential(self):
        from controller.subscription_store import (
            save_subscription,
            validate_subscription,
        )

        save_subscription("openai", auth_mode="api_key_from_subscription")
        result = validate_subscription("openai")
        self.assertEqual(result["validation_status"], "invalid")

    def test_validate_expired_token(self):
        from controller.subscription_store import (
            save_subscription,
            validate_subscription,
        )

        save_subscription(
            "anthropic",
            auth_mode="session_token",
            session_token="sess-abcdefghijklmnop1234567890",
            expires_at=int(time.time()) - 3600,
        )
        result = validate_subscription("anthropic")
        self.assertEqual(result["validation_status"], "expired")

    def test_credential_for_provider_api_key(self):
        from controller.subscription_store import (
            save_subscription,
            subscription_api_key_for_provider,
            subscription_credential_for_provider,
        )

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-test-12345678901234567890")

        cred = subscription_credential_for_provider("openai")
        self.assertTrue(cred["usable"])
        self.assertEqual(cred["status"], "ready")
        self.assertEqual(cred["api_key"], "sk-test-12345678901234567890")

        api_key = subscription_api_key_for_provider("openai")
        self.assertEqual(api_key, "sk-test-12345678901234567890")

    def test_credential_for_inactive_provider(self):
        from controller.subscription_store import (
            activate_subscription,
            save_subscription,
            subscription_api_key_for_provider,
            subscription_credential_for_provider,
        )

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-test-12345678901234567890")
        activate_subscription("openai", False)

        cred = subscription_credential_for_provider("openai")
        self.assertFalse(cred["usable"])
        self.assertEqual(cred["status"], "inactive")

        api_key = subscription_api_key_for_provider("openai")
        self.assertEqual(api_key, "")

    def test_credential_for_unsupported_provider(self):
        from controller.subscription_store import subscription_credential_for_provider

        cred = subscription_credential_for_provider("nonexistent")
        self.assertFalse(cred["usable"])
        self.assertEqual(cred["status"], "unsupported")

    def test_masked_credential(self):
        from controller.subscription_store import (
            save_subscription,
            subscription_status,
        )

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-test-12345678901234567890")
        status = subscription_status()
        masked = status["openai"]["masked_credential"]
        self.assertTrue(masked.startswith("sk-t"))
        self.assertTrue(masked.endswith("7890"))
        self.assertIn("...", masked)

    def test_store_file_permissions(self):
        from controller.subscription_store import save_subscription

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-test-12345678901234567890")
        path = Path(self.store_path)
        self.assertTrue(path.exists())
        mode = path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600, f"Expected 0600, got {oct(mode)}")


class TestRooCliRuntimeSubscriptionIntegration(unittest.TestCase):
    """Test that roo_cli_runtime can resolve keys from subscriptions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "test_subscriptions.json")
        self.key_store_path = os.path.join(self.tmpdir, "test_api_keys.json")
        self.env_patcher = patch.dict(os.environ, {
            "WINTRIP_SUBSCRIPTION_STORE": self.store_path,
            "WINTRIP_API_KEY_STORE": self.key_store_path,
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        for path in (self.store_path, self.key_store_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        try:
            os.rmdir(self.tmpdir)
        except Exception:
            pass

    def test_resolve_from_subscription(self):
        from controller.roo_cli_runtime import resolve_api_key_for_provider
        from controller.subscription_store import save_subscription

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-sub-test-123456789012")

        result = resolve_api_key_for_provider("openai")
        self.assertTrue(result["usable"])
        self.assertEqual(result["source"], "subscription")
        self.assertEqual(result["key"], "sk-sub-test-123456789012")

    def test_explicit_key_takes_priority(self):
        from controller.roo_cli_runtime import resolve_api_key_for_provider
        from controller.subscription_store import save_subscription

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-sub-test-123456789012")

        result = resolve_api_key_for_provider("openai", explicit_key="sk-explicit-99999999")
        self.assertTrue(result["usable"])
        self.assertEqual(result["source"], "explicit")
        self.assertEqual(result["key"], "sk-explicit-99999999")

    def test_env_takes_priority_over_subscription(self):
        from controller.roo_cli_runtime import resolve_api_key_for_provider
        from controller.subscription_store import save_subscription

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-sub-test-123456789012")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-88888888"}):
            result = resolve_api_key_for_provider("openai")
            self.assertTrue(result["usable"])
            self.assertEqual(result["source"], "env")

    def test_api_key_available_with_subscription(self):
        from controller.roo_cli_runtime import api_key_available_for_provider
        from controller.subscription_store import save_subscription

        save_subscription("anthropic", auth_mode="api_key_from_subscription", api_key="sk-ant-sub-12345678901234")

        provider_map = {
            "status": "mapped",
            "cockpit_provider": "anthropic",
            "roo_provider": "anthropic",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
        self.assertTrue(api_key_available_for_provider("anthropic", provider_map))

    def test_no_key_when_subscription_inactive(self):
        from controller.roo_cli_runtime import resolve_api_key_for_provider
        from controller.subscription_store import activate_subscription, save_subscription

        save_subscription("openai", auth_mode="api_key_from_subscription", api_key="sk-sub-test-123456789012")
        activate_subscription("openai", False)

        result = resolve_api_key_for_provider("openai")
        self.assertFalse(result["usable"])


if __name__ == "__main__":
    unittest.main()
