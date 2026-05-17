import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.ollama_client import OllamaClient
from controller.ollama_router import (
    ALLOWED_OLLAMA_MODELS,
    allowed_available_models,
    ollama_router_status,
    route_ollama_model,
    select_ollama_model,
)


EXPECTED_ALLOWLIST = (
    "gpt-oss:120b-cloud",
    "ouroboros",
    "deepseek-coder:latest",
    "llama2-uncensored:latest",
    "devstral:latest",
    "llama3.2:latest",
    "mistral:latest",
    "codellama:13b",
    "llama3:8b",
    "llama3:latest",
    "gemma4:latest",
    "phi3:latest",
)


class FakeOllamaClient(OllamaClient):
    def __init__(self, models):
        self._models = list(models)
        super().__init__(model="llama3.2:latest", base_url="http://localhost:11434/api")

    def list_models(self):
        return list(self._models)


class TestOllamaRouter(unittest.TestCase):
    def test_allowlist_is_exact(self):
        self.assertEqual(ALLOWED_OLLAMA_MODELS, EXPECTED_ALLOWLIST)

    def test_filters_disallowed_models_from_availability(self):
        models = [
            "qwen2.5:latest",
            "gpt-oss:120b-cloud",
            {"name": "ouroboros:latest"},
            {"name": "mistral:latest"},
            {"model": "phi4:latest"},
            {"id": "llama3.2:latest"},
            "gemma2:latest",
        ]

        self.assertEqual(
            allowed_available_models(models),
            ("gpt-oss:120b-cloud", "ouroboros", "mistral:latest", "llama3.2:latest"),
        )

    def test_code_role_prefers_deepseek_then_codellama_then_devstral(self):
        self.assertEqual(
            select_ollama_model(role="self_modification", list_models=lambda: ["codellama:13b", "devstral:latest"]),
            "codellama:13b",
        )
        self.assertEqual(
            select_ollama_model(role="code", list_models=lambda: ["devstral:latest"]),
            "devstral:latest",
        )
        self.assertEqual(
            select_ollama_model(role="Developer", list_models=lambda: []),
            "deepseek-coder:latest",
        )

    def test_quick_internal_role_prefers_phi3_then_mistral_then_llama32(self):
        self.assertEqual(
            select_ollama_model(role="quick", list_models=lambda: ["mistral:latest", "llama3.2:latest"]),
            "mistral:latest",
        )
        self.assertEqual(
            select_ollama_model(role="internal", list_models=lambda: ["llama3.2:latest"]),
            "llama3.2:latest",
        )

    def test_critic_test_research_role_prefers_gpt_oss_then_mistral_then_llama(self):
        self.assertEqual(
            select_ollama_model(role="research", list_models=lambda: ["gpt-oss:120b-cloud", "mistral:latest"]),
            "gpt-oss:120b-cloud",
        )
        self.assertEqual(
            select_ollama_model(role="critic", list_models=lambda: ["llama3:latest", "llama3.2:latest"]),
            "llama3.2:latest",
        )
        self.assertEqual(
            select_ollama_model(role="test", list_models=lambda: ["llama3:latest"]),
            "llama3:latest",
        )
        self.assertEqual(
            select_ollama_model(role="research", list_models=lambda: ["phi3:latest", "mistral:latest"]),
            "mistral:latest",
        )

    def test_default_role_prefers_llama32_then_llama3_then_mistral_then_phi3(self):
        self.assertEqual(
            select_ollama_model(role="unknown", list_models=lambda: ["phi3:latest", "mistral:latest"]),
            "mistral:latest",
        )
        self.assertEqual(
            select_ollama_model(role="", list_models=lambda: ["llama3:latest", "mistral:latest"]),
            "llama3:latest",
        )

    def test_requested_allowed_model_wins_only_when_allowed_and_available(self):
        self.assertEqual(
            select_ollama_model(requested="phi3", role="code", list_models=lambda: ["phi3:latest", "codellama:13b"]),
            "phi3:latest",
        )
        self.assertEqual(
            select_ollama_model(
                requested="qwen2.5:latest",
                role="quick",
                list_models=lambda: ["qwen2.5:latest", "mistral:latest"],
            ),
            "mistral:latest",
        )
        self.assertEqual(
            select_ollama_model(requested="phi3", role="default", list_models=lambda: ["mistral:latest"]),
            "mistral:latest",
        )

    def test_empty_or_failing_list_models_never_requires_live_ollama(self):
        def broken_list_models():
            raise RuntimeError("ollama not running")

        self.assertEqual(
            select_ollama_model(role="code", list_models=broken_list_models),
            "deepseek-coder:latest",
        )
        self.assertEqual(
            select_ollama_model(requested="phi3", role="default", list_models=lambda: []),
            "phi3:latest",
        )
        self.assertEqual(
            select_ollama_model(role="default", list_models=lambda: []),
            "gpt-oss:120b-cloud",
        )

    def test_route_details_and_status_are_status_endpoint_ready(self):
        route = route_ollama_model(role="research", list_models=lambda: ["mistral:latest"])
        self.assertEqual(route.selected, "mistral:latest")
        self.assertEqual(route.role, "critic")
        self.assertEqual(route.available_models, ("mistral:latest",))

        status = ollama_router_status(list_models=lambda: ["mistral:latest", "qwen2.5:latest"])
        self.assertEqual(status["available_models"], ["mistral:latest"])
        self.assertEqual(status["allowed_models"], list(EXPECTED_ALLOWLIST))
        self.assertIn("default", status["roles"])

    def test_ollama_client_delegates_selection_to_allowlist_router(self):
        client = FakeOllamaClient(["deepseek-coder:latest", "qwen2.5:latest", "mistral:latest"])

        self.assertEqual(client.select_model(role="code"), "deepseek-coder:latest")
        self.assertEqual(client.select_model(requested="qwen2.5:latest", role="quick"), "mistral:latest")


if __name__ == "__main__":
    unittest.main()
