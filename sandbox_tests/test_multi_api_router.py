import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.multi_api_router import HTTPX_HTTP_ERROR, MultiAPIRouter, PROVIDERS


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


class FakeHTTPStatusError(HTTPX_HTTP_ERROR):
    def __init__(self, response, message="Client error"):
        super().__init__(message)
        self.response = response


class ErrorResponse(FakeResponse):
    def __init__(self, payload, status_code=400, text=""):
        super().__init__(payload)
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        self.raise_for_status_called = True
        raise FakeHTTPStatusError(self)


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


class SequentialAsyncClient:
    def __init__(self, factory):
        self.factory = factory

    async def __aenter__(self):
        self.factory.entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.factory.exited += 1

    async def post(self, url, headers=None, json=None):
        self.factory.posts.append(
            {"url": url, "headers": dict(headers or {}), "json": dict(json or {})}
        )
        return self.factory.responses.pop(0)


class SequentialFactory:
    def __init__(self, responses):
        self.responses = list(responses)
        self.posts = []
        self.calls = 0
        self.entered = 0
        self.exited = 0

    def __call__(self):
        self.calls += 1
        return SequentialAsyncClient(self)


class TestMultiAPIRouter(unittest.IsolatedAsyncioTestCase):
    async def test_missing_keys_short_circuit_before_any_network_client(self):
        aliases = [
            ("openai", "openai"),
            ("chatgpt", "openai"),
            ("ChatGPT Pro", "openai"),
            ("anthropic", "anthropic"),
            ("Claude Opus", "anthropic"),
            ("DeepSeek", "deepseek"),
            ("deekseek", "deepseek"),
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
                "DeepSeek",
                {"deepseek": "deepseek-key"},
                {"choices": [{"message": {"content": "deepseek ok"}}]},
                "deepseek",
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

    async def test_google_tools_are_deduped_and_schema_sanitized(self):
        factory = RecordingFactory({"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]})
        router = MultiAPIRouter(api_keys={"google": "google-key"}, client_factory=factory)
        tools = [
            NEUTRAL_TOOL,
            {
                "name": "memory_search",
                "description": "Duplicate should be ignored.",
                "parameters": {
                    "type": "object",
                    "properties": {"other": {"type": "string"}},
                    "required": ["other"],
                },
            },
            {
                "name": "external_capabilities_status",
                "description": "No-argument status probe.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "function": {
                    "name": "remember_thing",
                    "description": "Remember a short note.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Note text."},
                            "empty": {"type": "object", "properties": {}},
                        },
                        "required": ["text", "empty"],
                    },
                },
            },
        ]

        result = await router.route_chat("google", "gemini-test", "Hello", tools=tools)

        self.assertEqual(result["status"], "success")
        declarations = factory.client.posts[0]["json"]["tools"][0]["functionDeclarations"]
        names = [tool["name"] for tool in declarations]
        self.assertEqual(names.count("memory_search"), 1)
        self.assertEqual(names.count("external_capabilities_status"), 1)
        self.assertEqual(names.count("remember_thing"), 1)

        status_tool = next(tool for tool in declarations if tool["name"] == "external_capabilities_status")
        self.assertNotIn("parameters", status_tool)

        remember_tool = next(tool for tool in declarations if tool["name"] == "remember_thing")
        parameters = remember_tool["parameters"]
        self.assertEqual(parameters["required"], ["text"])
        self.assertIn("text", parameters["properties"])
        self.assertNotIn("empty", parameters["properties"])

    async def test_google_400_with_tools_retries_once_without_tool_schemas(self):
        factory = SequentialFactory(
            [
                ErrorResponse({"error": {"message": "Invalid function declaration"}}),
                FakeResponse({"candidates": [{"content": {"parts": [{"text": "fallback ok"}]}}]}),
            ]
        )
        router = MultiAPIRouter(api_keys={"google": "google-key"}, client_factory=factory)

        result = await router.route_chat("google", "gemini-test", "Hello", tools=[NEUTRAL_TOOL])

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["response"], "fallback ok")
        self.assertTrue(result["tool_schemas_dropped"])
        self.assertEqual(factory.calls, 2)
        self.assertEqual(factory.entered, 2)
        self.assertEqual(factory.exited, 2)
        self.assertIn("tools", factory.posts[0]["json"])
        self.assertNotIn("tools", factory.posts[1]["json"])

    async def test_provider_error_payload_includes_scrubbed_status_and_body(self):
        factory = SequentialFactory([ErrorResponse({"error": {"message": "Model not found"}})])
        router = MultiAPIRouter(api_keys={"google": "google-key"}, client_factory=factory)

        result = await router.route_chat("google", "gemini-test", "Hello")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["provider"], "google")
        self.assertEqual(result["provider_status_code"], 400)
        self.assertEqual(result["provider_error"], "Model not found")
        self.assertEqual(result["error"], "Model not found")

    async def test_deepseek_model_prefix_routes_to_openai_compatible_endpoint(self):
        factory = RecordingFactory({"choices": [{"message": {"content": "deepseek ok"}}]})
        router = MultiAPIRouter(api_keys={"DEEPSEEK_API_KEY": "deepseek-env-key"}, client_factory=factory)

        result = await router.route_chat("", "deepseek-reasoner", "Hello", tools=[NEUTRAL_TOOL])

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["model"], "deepseek-reasoner")
        post = factory.client.posts[0]
        self.assertEqual(post["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(post["headers"]["authorization"], "Bearer deepseek-env-key")
        self.assertEqual(post["json"]["model"], "deepseek-reasoner")
        self.assertEqual(post["json"]["tools"][0]["function"]["name"], "memory_search")


if __name__ == "__main__":
    unittest.main()
