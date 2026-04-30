import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.multi_api_router import MultiAPIRouter, PROVIDERS


NEUTRAL_TOOL = {
    "name": "memory_search",
    "description": "Search local memory without executing it in the provider router.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True

    def json(self):
        return self.payload


class RecordingAsyncClient:
    def __init__(self, response_payload):
        self.response = FakeResponse(response_payload)
        self.posts = []
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True

    async def post(self, url, headers=None, json=None):
        self.posts.append({"url": url, "headers": dict(headers or {}), "json": dict(json or {})})
        return self.response


class RecordingFactory:
    def __init__(self, response_payload):
        self.client = RecordingAsyncClient(response_payload)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.client


class TestMultiAPIRouter(unittest.IsolatedAsyncioTestCase):
    async def test_missing_keys_short_circuit_before_any_network_client(self):
        aliases = [
            ("openai", "openai"),
            ("chatgpt", "openai"),
            ("ChatGPT Pro", "openai"),
            ("anthropic", "anthropic"),
            ("Claude Opus", "anthropic"),
            ("xai", "xai"),
            ("Grok", "xai"),
            ("google", "google"),
            ("Gemini", "google"),
            ("mistral", "mistral"),
        ]

        with patch.dict(os.environ, {}, clear=True):
            for provider, expected_provider in aliases:
                with self.subTest(provider=provider):
                    calls = 0

                    def fail_if_called():
                        nonlocal calls
                        calls += 1
                        raise AssertionError("network client factory should not be created without a key")

                    router = MultiAPIRouter(client_factory=fail_if_called)
                    result = await router.route_chat(provider, "", "ping")

                    self.assertEqual(calls, 0)
                    self.assertEqual(result["status"], "disabled")
                    self.assertEqual(result["reason"], "missing_key")
                    self.assertEqual(result["provider"], expected_provider)
                    self.assertFalse(result["network_call_made"])
                    self.assertIn("API key", result["message"])

    async def test_ollama_and_unknown_providers_never_make_external_calls(self):
        calls = 0

        def fail_if_called():
            nonlocal calls
            calls += 1
            raise AssertionError("local or unsupported routes must not create an HTTP client")

        router = MultiAPIRouter(client_factory=fail_if_called)
        ollama = await router.route_chat("local", "llama3.2:latest", "ping")
        unknown = await router.route_chat("not-a-provider", "", "ping")

        self.assertEqual(calls, 0)
        self.assertEqual(ollama["provider"], "ollama")
        self.assertEqual(ollama["status"], "unsupported")
        self.assertTrue(ollama["local_only"])
        self.assertFalse(ollama["network_call_made"])
        self.assertEqual(unknown["status"], "unsupported")
        self.assertEqual(unknown["reason"], "unsupported_provider")
        self.assertFalse(unknown["network_call_made"])

    async def test_openai_path_uses_official_chat_payload_without_real_call(self):
        factory = RecordingFactory(
            {
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "memory_search", "arguments": "{\"query\":\"x\"}"},
                                }
                            ],
                        }
                    }
                ]
            }
        )
        router = MultiAPIRouter(api_keys={"openai": "openai-test-key"}, client_factory=factory)

        result = await router.route_chat(
            "chatgpt",
            "gpt-test",
            "Hello",
            system_prompt="System",
            history=[{"role": "assistant", "content": "Earlier"}],
            tools=[NEUTRAL_TOOL],
        )

        self.assertEqual(factory.calls, 1)
        self.assertTrue(factory.client.entered)
        self.assertTrue(factory.client.exited)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["response"], "ok")
        self.assertFalse(result["fake_tool_success"])

        post = factory.client.posts[0]
        self.assertEqual(post["url"], PROVIDERS["openai"].endpoint)
        self.assertEqual(post["headers"]["authorization"], "Bearer openai-test-key")
        payload = post["json"]
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "System"},
                {"role": "assistant", "content": "Earlier"},
                {"role": "user", "content": "Hello"},
            ],
        )
        self.assertNotIn("prompt", payload)
        self.assertNotIn("input", payload)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["tools"][0]["type"], "function")
        self.assertEqual(payload["tools"][0]["function"]["name"], "memory_search")

    async def test_provider_specific_payloads_are_mapped_from_neutral_tools(self):
        cases = [
            (
                "Claude Opus",
                {"anthropic": "anthropic-key"},
                {"content": [{"type": "text", "text": "claude ok"}]},
                "anthropic",
            ),
            (
                "Grok",
                {"xai": "xai-key"},
                {"choices": [{"message": {"content": "grok ok"}}]},
                "xai",
            ),
            (
                "Gemini",
                {"google": "google-key"},
                {"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]},
                "google",
            ),
            (
                "Mistral",
                {"mistral": "mistral-key"},
                {"choices": [{"message": {"content": "mistral ok"}}]},
                "mistral",
            ),
        ]

        for provider_alias, keys, response_payload, expected_provider in cases:
            with self.subTest(provider=provider_alias):
                factory = RecordingFactory(response_payload)
                router = MultiAPIRouter(api_keys=keys, client_factory=factory)

                result = await router.route_chat(
                    provider_alias,
                    "",
                    "Hello",
                    system_prompt="System",
                    history=[{"role": "assistant", "content": "Earlier"}],
                    tools=[NEUTRAL_TOOL],
                )

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["provider"], expected_provider)
                self.assertFalse(result["fake_tool_success"])
                self.assertEqual(factory.calls, 1)
                post = factory.client.posts[0]
                payload = post["json"]

                if expected_provider == "anthropic":
                    self.assertEqual(post["url"], PROVIDERS["anthropic"].endpoint)
                    self.assertEqual(post["headers"]["x-api-key"], "anthropic-key")
                    self.assertEqual(payload["model"], PROVIDERS["anthropic"].default_model)
                    self.assertEqual(payload["system"], "System")
                    self.assertNotIn({"role": "system", "content": "System"}, payload["messages"])
                    self.assertEqual(payload["tools"][0]["name"], "memory_search")
                    self.assertIn("input_schema", payload["tools"][0])
                elif expected_provider == "google":
                    self.assertEqual(
                        post["url"],
                        PROVIDERS["google"].endpoint.format(model=PROVIDERS["google"].default_model),
                    )
                    self.assertEqual(post["headers"]["x-goog-api-key"], "google-key")
                    self.assertEqual(payload["system_instruction"]["parts"][0]["text"], "System")
                    self.assertEqual(payload["contents"][0]["role"], "model")
                    self.assertEqual(payload["contents"][-1]["role"], "user")
                    self.assertEqual(payload["tools"][0]["functionDeclarations"][0]["name"], "memory_search")
                else:
                    self.assertEqual(post["url"], PROVIDERS[expected_provider].endpoint)
                    self.assertEqual(
                        post["headers"]["authorization"],
                        f"Bearer {expected_provider}-key",
                    )
                    self.assertEqual(payload["model"], PROVIDERS[expected_provider].default_model)
                    self.assertEqual(payload["tools"][0]["type"], "function")
                    self.assertEqual(payload["tools"][0]["function"]["name"], "memory_search")


if __name__ == "__main__":
    unittest.main()
