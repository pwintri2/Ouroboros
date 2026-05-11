"""Provider-safe async middleware for commercial chat APIs.

The router is deliberately conservative: provider aliases are normalized,
missing API keys short-circuit before any HTTP client is created, and tests can
inject a fake async client factory for every network path.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any


class MissingHTTPXError(RuntimeError):
    """Raised when a real HTTP call is requested without httpx installed."""


try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - exercised by bare sandboxes.
    httpx = None  # type: ignore[assignment]

    class _HTTPXHTTPError(Exception):
        pass

    HTTPX_HTTP_ERROR = _HTTPXHTTPError
else:
    HTTPX_HTTP_ERROR = httpx.HTTPError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

JsonDict = dict[str, Any]
AsyncClientFactory = Callable[[], Any]


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    aliases: tuple[str, ...]
    key_env: tuple[str, ...]
    endpoint: str
    api_family: str
    default_model: str
    transport: str = "https"
    supports_tools: bool = True


PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        provider="openai",
        aliases=("openai", "chatgpt", "chatgpt pro", "gpt"),
        key_env=("OPENAI_API_KEY",),
        endpoint="https://api.openai.com/v1/chat/completions",
        api_family="openai_chat",
        default_model="gpt-4o",
    ),
    "anthropic": ProviderConfig(
        provider="anthropic",
        aliases=("anthropic", "claude", "claude opus"),
        key_env=("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
        endpoint="https://api.anthropic.com/v1/messages",
        api_family="anthropic_messages",
        default_model="claude-3-opus-20240229",
    ),
    "deepseek": ProviderConfig(
        provider="deepseek",
        aliases=("deepseek", "deep seek", "deepseek api", "deekseek", "deepseek chat", "deepseek reasoner"),
        key_env=("DEEPSEEK_API_KEY",),
        endpoint="https://api.deepseek.com/chat/completions",
        api_family="openai_chat",
        default_model="deepseek-v4-flash",
    ),
    "xai": ProviderConfig(
        provider="xai",
        aliases=("xai", "x.ai", "grok"),
        key_env=("XAI_API_KEY", "GROK_API_KEY"),
        endpoint="https://api.x.ai/v1/chat/completions",
        api_family="openai_chat",
        default_model="grok-2-latest",
    ),
    "google": ProviderConfig(
        provider="google",
        aliases=("google", "gemini"),
        key_env=("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        endpoint="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        api_family="gemini_generate_content",
        default_model="gemini-2.5-flash",
    ),
    "mistral": ProviderConfig(
        provider="mistral",
        aliases=("mistral",),
        key_env=("MISTRAL_API_KEY",),
        endpoint="https://api.mistral.ai/v1/chat/completions",
        api_family="openai_chat",
        default_model="mistral-large-latest",
    ),
    "ollama": ProviderConfig(
        provider="ollama",
        aliases=("ollama", "local"),
        key_env=(),
        endpoint="",
        api_family="local_status",
        default_model="",
        transport="local",
        supports_tools=False,
    ),
}


def _normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


PROVIDER_ALIASES: dict[str, str] = {
    _normalize_label(alias): config.provider
    for config in PROVIDERS.values()
    for alias in config.aliases
}

MODEL_ALIASES: dict[str, tuple[str, str]] = {
    "chatgpt pro": ("openai", PROVIDERS["openai"].default_model),
    "chatgpt": ("openai", PROVIDERS["openai"].default_model),
    "claude opus": ("anthropic", PROVIDERS["anthropic"].default_model),
    "claude": ("anthropic", PROVIDERS["anthropic"].default_model),
    "deepseek": ("deepseek", PROVIDERS["deepseek"].default_model),
    "deep seek": ("deepseek", PROVIDERS["deepseek"].default_model),
    "deepseek api": ("deepseek", PROVIDERS["deepseek"].default_model),
    "deekseek": ("deepseek", PROVIDERS["deepseek"].default_model),
    "deepseek chat": ("deepseek", "deepseek-chat"),
    "deepseek reasoner": ("deepseek", "deepseek-reasoner"),
    "grok": ("xai", PROVIDERS["xai"].default_model),
    "gemini": ("google", PROVIDERS["google"].default_model),
    "mistral": ("mistral", PROVIDERS["mistral"].default_model),
}

MODEL_PREFIX_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("gpt", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("claude", "anthropic"),
    ("deepseek", "deepseek"),
    ("grok", "xai"),
    ("gemini", "google"),
    ("mistral", "mistral"),
)


class MultiAPIRouter:
    """Route chat requests to supported providers without hidden side effects."""

    def __init__(
        self,
        api_keys: Mapping[str, str | None] | None = None,
        client_factory: AsyncClientFactory | None = None,
        timeout: float = 60.0,
        local_handler: Callable[..., Any] | None = None,
    ) -> None:
        self.timeout = timeout
        self.client_factory = client_factory or self._default_client_factory
        self.local_handler = local_handler
        self.api_keys = self._load_api_keys(api_keys or {})

    def _default_client_factory(self) -> Any:
        if httpx is None:
            raise MissingHTTPXError("httpx is required for real external provider calls")
        return httpx.AsyncClient(timeout=self.timeout)

    def _load_api_keys(self, injected: Mapping[str, str | None]) -> dict[str, str]:
        keys: dict[str, str] = {}
        normalized_injected = {_normalize_label(key): value for key, value in injected.items()}
        for provider, config in PROVIDERS.items():
            value = normalized_injected.get(provider)
            if not value:
                for alias in config.aliases:
                    value = normalized_injected.get(_normalize_label(alias))
                    if value:
                        break
            if not value:
                for env_name in config.key_env:
                    value = injected.get(env_name) or os.getenv(env_name)
                    if value:
                        break
            if value:
                keys[provider] = str(value)
        return keys

    async def route_chat(
        self,
        provider: str,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        history: Sequence[Mapping[str, Any]] | None = None,
    ) -> JsonDict:
        """Entry point for provider-neutral chat calls.

        ``tools`` are only schemas. The router forwards them to model APIs and
        returns model-requested tool calls, but it never executes a tool or
        invents tool success.
        """

        config, resolved_model, alias_source = self.resolve_provider_model(provider, model)
        if config is None:
            return self._unsupported_provider_payload(provider, model, alias_source)

        if config.provider == "ollama":
            return await self._route_local(
                resolved_model,
                prompt,
                system_prompt=system_prompt,
                history=history,
                alias_source=alias_source,
            )

        api_key = self.api_keys.get(config.provider)
        if not api_key:
            return self._missing_key_payload(config, resolved_model, alias_source)

        try:
            if config.api_family == "openai_chat":
                return await self._call_openai_compatible(
                    config,
                    api_key,
                    resolved_model,
                    prompt,
                    system_prompt=system_prompt,
                    tools=tools,
                    history=history,
                    alias_source=alias_source,
                )
            if config.api_family == "anthropic_messages":
                return await self._call_anthropic(
                    config,
                    api_key,
                    resolved_model,
                    prompt,
                    system_prompt=system_prompt,
                    tools=tools,
                    history=history,
                    alias_source=alias_source,
                )
            if config.api_family == "gemini_generate_content":
                return await self._call_google(
                    config,
                    api_key,
                    resolved_model,
                    prompt,
                    system_prompt=system_prompt,
                    tools=tools,
                    history=history,
                    alias_source=alias_source,
                )
        except MissingHTTPXError as exc:
            logger.warning("Provider transport unavailable for %s: %s", config.provider, exc)
            return self._error_payload(config, resolved_model, exc, alias_source, network_call_made=False)
        except HTTPX_HTTP_ERROR as exc:
            logger.warning("Provider HTTP error for %s: %s", config.provider, exc)
            return self._error_payload(config, resolved_model, exc, alias_source)
        except Exception as exc:
            logger.exception("Provider routing error for %s", config.provider)
            return self._error_payload(config, resolved_model, exc, alias_source)

        return self._unsupported_provider_payload(provider, model, alias_source)

    def resolve_provider_model(
        self,
        provider: str | None,
        model: str | None,
    ) -> tuple[ProviderConfig | None, str, str]:
        provider_label = _normalize_label(provider)
        model_label = _normalize_label(model)

        provider_id = PROVIDER_ALIASES.get(provider_label)
        alias_source = "provider" if provider_id else "unknown"

        if not provider_id and provider_label in MODEL_ALIASES:
            provider_id, alias_model = MODEL_ALIASES[provider_label]
            alias_source = "provider_alias"
            if not model:
                return PROVIDERS[provider_id], alias_model, alias_source

        if not provider_id and model_label in MODEL_ALIASES:
            provider_id, alias_model = MODEL_ALIASES[model_label]
            alias_source = "model_alias"
            return PROVIDERS[provider_id], alias_model, alias_source

        if not provider_id:
            provider_id = self._infer_provider_from_model(model)
            if provider_id:
                alias_source = "model_prefix"

        if not provider_id:
            return None, str(model or ""), alias_source

        config = PROVIDERS[provider_id]
        resolved_model = self._resolve_model(config, model, provider)
        return config, resolved_model, alias_source

    def _infer_provider_from_model(self, model: str | None) -> str:
        label = _normalize_label(model)
        if not label:
            return ""
        for prefix, provider in MODEL_PREFIX_PROVIDERS:
            if label.startswith(prefix):
                return provider
        return ""

    def _resolve_model(
        self,
        config: ProviderConfig,
        model: str | None,
        provider: str | None = None,
    ) -> str:
        model_label = _normalize_label(model)
        if model_label in MODEL_ALIASES:
            alias_provider, alias_model = MODEL_ALIASES[model_label]
            if alias_provider == config.provider:
                return alias_model

        provider_label = _normalize_label(provider)
        if not model and provider_label in MODEL_ALIASES:
            alias_provider, alias_model = MODEL_ALIASES[provider_label]
            if alias_provider == config.provider:
                return alias_model

        return str(model or config.default_model or "").strip()

    async def _call_openai_compatible(
        self,
        config: ProviderConfig,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        history: Sequence[Mapping[str, Any]] | None = None,
        alias_source: str = "",
    ) -> JsonDict:
        payload = self._openai_chat_payload(model, prompt, system_prompt, tools, history)
        async with self._managed_client() as client:
            response = await client.post(
                config.endpoint,
                headers=self._bearer_headers(api_key),
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        message = self._first_openai_message(data)
        return self._success_payload(
            config,
            model,
            data,
            response_text=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
            alias_source=alias_source,
        )

    async def _call_anthropic(
        self,
        config: ProviderConfig,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        history: Sequence[Mapping[str, Any]] | None = None,
        alias_source: str = "",
    ) -> JsonDict:
        payload = self._anthropic_payload(model, prompt, system_prompt, tools, history)
        async with self._managed_client() as client:
            response = await client.post(
                config.endpoint,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        response_text, tool_calls = self._parse_anthropic_content(data)
        return self._success_payload(
            config,
            model,
            data,
            response_text=response_text,
            tool_calls=tool_calls,
            alias_source=alias_source,
        )

    async def _call_google(
        self,
        config: ProviderConfig,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        history: Sequence[Mapping[str, Any]] | None = None,
        alias_source: str = "",
    ) -> JsonDict:
        payload = self._google_payload(model, prompt, system_prompt, tools, history)
        endpoint = config.endpoint.format(model=model)
        headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        retried_without_tools = False
        try:
            async with self._managed_client() as client:
                response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
        except HTTPX_HTTP_ERROR as exc:
            if payload.get("tools") and _http_status_code(exc) == 400:
                retried_without_tools = True
                fallback_payload = dict(payload)
                fallback_payload.pop("tools", None)
                async with self._managed_client() as client:
                    response = await client.post(endpoint, headers=headers, json=fallback_payload)
                response.raise_for_status()
            else:
                raise
        data = response.json()
        response_text, tool_calls = self._parse_google_content(data)
        result = self._success_payload(
            config,
            model,
            data,
            response_text=response_text,
            tool_calls=tool_calls,
            alias_source=alias_source,
        )
        if retried_without_tools:
            result["provider_warning"] = "Gemini rejected tool declarations; request was retried once without tools."
            result["tool_schemas_dropped"] = True
        return result

    async def _route_local(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        history: Sequence[Mapping[str, Any]] | None = None,
        alias_source: str = "",
    ) -> JsonDict:
        if self.local_handler is None:
            return {
                "status": "unsupported",
                "reason": "local_route_not_wired",
                "provider": "ollama",
                "model": model,
                "available": False,
                "enabled": False,
                "local_only": True,
                "network_call_made": False,
                "alias_source": alias_source,
                "message": "Use the dedicated Ollama router/client for local chat; no external call was made.",
            }

        result = self.local_handler(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            history=list(history or []),
        )
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, dict):
            result.setdefault("provider", "ollama")
            result.setdefault("model", model)
            result.setdefault("local_only", True)
            result.setdefault("network_call_made", False)
            result.setdefault("fake_tool_success", False)
            return result
        return {
            "status": "success",
            "provider": "ollama",
            "model": model,
            "response": str(result),
            "local_only": True,
            "network_call_made": False,
            "fake_tool_success": False,
        }

    def _openai_chat_payload(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None,
        tools: Sequence[Mapping[str, Any]] | None,
        history: Sequence[Mapping[str, Any]] | None,
    ) -> JsonDict:
        payload: JsonDict = {
            "model": model,
            "messages": self._openai_messages(prompt, system_prompt, history),
        }
        provider_tools = self._openai_tools(tools)
        if provider_tools:
            payload["tools"] = provider_tools
            payload["tool_choice"] = "auto"
        return payload

    def _anthropic_payload(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None,
        tools: Sequence[Mapping[str, Any]] | None,
        history: Sequence[Mapping[str, Any]] | None,
    ) -> JsonDict:
        payload: JsonDict = {
            "model": model,
            "max_tokens": 4096,
            "messages": self._anthropic_messages(prompt, history),
        }
        if system_prompt:
            payload["system"] = system_prompt
        provider_tools = self._anthropic_tools(tools)
        if provider_tools:
            payload["tools"] = provider_tools
        return payload

    def _google_payload(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None,
        tools: Sequence[Mapping[str, Any]] | None,
        history: Sequence[Mapping[str, Any]] | None,
    ) -> JsonDict:
        payload: JsonDict = {"contents": self._google_contents(prompt, history)}
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        declarations = self._google_function_declarations(tools)
        if declarations:
            payload["tools"] = [{"functionDeclarations": declarations}]
        return payload

    def _openai_messages(
        self,
        prompt: str,
        system_prompt: str | None,
        history: Sequence[Mapping[str, Any]] | None,
    ) -> list[JsonDict]:
        messages: list[JsonDict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for item in history or []:
            role = str(item.get("role") or "user")
            content = item.get("content", "")
            if role in {"system", "user", "assistant", "tool"}:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _anthropic_messages(
        self,
        prompt: str,
        history: Sequence[Mapping[str, Any]] | None,
    ) -> list[JsonDict]:
        messages: list[JsonDict] = []
        for item in history or []:
            role = str(item.get("role") or "user")
            if role == "system":
                continue
            if role not in {"user", "assistant"}:
                role = "user"
            messages.append({"role": role, "content": item.get("content", "")})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _google_contents(
        self,
        prompt: str,
        history: Sequence[Mapping[str, Any]] | None,
    ) -> list[JsonDict]:
        contents: list[JsonDict] = []
        last_role = ""
        for item in history or []:
            role = str(item.get("role") or "user")
            if role == "system":
                continue
            gemini_role = "model" if role == "assistant" else "user"
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            if contents and gemini_role == last_role:
                contents[-1]["parts"].append({"text": content})
            else:
                contents.append({"role": gemini_role, "parts": [{"text": content}]})
                last_role = gemini_role
        clean_prompt = str(prompt or "").strip()
        if contents and last_role == "user":
            contents[-1]["parts"].append({"text": clean_prompt})
        else:
            contents.append({"role": "user", "parts": [{"text": clean_prompt}]})
        return contents

    def _openai_tools(self, tools: Sequence[Mapping[str, Any]] | None) -> list[JsonDict]:
        normalized = self._normalized_function_tools(tools)
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
            for tool in normalized
        ]

    def _anthropic_tools(self, tools: Sequence[Mapping[str, Any]] | None) -> list[JsonDict]:
        return [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters") or {"type": "object", "properties": {}},
            }
            for tool in self._normalized_function_tools(tools)
        ]

    def _google_function_declarations(self, tools: Sequence[Mapping[str, Any]] | None) -> list[JsonDict]:
        declarations: list[JsonDict] = []
        for tool in self._normalized_function_tools(tools):
            declaration = {
                "name": tool["name"],
                "description": tool.get("description", ""),
            }
            parameters = _google_schema(tool.get("parameters"))
            if parameters is not None:
                declaration["parameters"] = parameters
            declarations.append(declaration)
        return declarations

    def _normalized_function_tools(self, tools: Sequence[Mapping[str, Any]] | None) -> list[JsonDict]:
        normalized: list[JsonDict] = []
        seen_names: set[str] = set()
        for tool in tools or []:
            if not isinstance(tool, Mapping):
                continue
            function = tool.get("function") if tool.get("type") == "function" else None
            if isinstance(function, Mapping):
                name = str(function.get("name") or "").strip()
                if name and name not in seen_names:
                    normalized.append(
                        {
                            "name": name,
                            "description": str(function.get("description") or ""),
                            "parameters": function.get("parameters") or function.get("input_schema"),
                        }
                    )
                    seen_names.add(name)
                continue

            name = str(tool.get("name") or "").strip()
            if name and name not in seen_names:
                normalized.append(
                    {
                        "name": name,
                        "description": str(tool.get("description") or ""),
                        "parameters": tool.get("parameters") or tool.get("input_schema"),
                    }
                )
                seen_names.add(name)
        return normalized

    def _first_openai_message(self, data: Mapping[str, Any]) -> JsonDict:
        choices = data.get("choices") or []
        if not choices:
            return {}
        first = choices[0] if isinstance(choices[0], Mapping) else {}
        message = first.get("message") if isinstance(first, Mapping) else {}
        return dict(message) if isinstance(message, Mapping) else {}

    def _parse_anthropic_content(self, data: Mapping[str, Any]) -> tuple[str, list[JsonDict]]:
        text_parts: list[str] = []
        tool_calls: list[JsonDict] = []
        for item in data.get("content") or []:
            if not isinstance(item, Mapping):
                continue
            if item.get("type") == "text":
                text_parts.append(str(item.get("text") or ""))
            elif item.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": item.get("id"),
                        "type": "function",
                        "function": {
                            "name": item.get("name"),
                            "arguments": json.dumps(item.get("input") or {}),
                        },
                    }
                )
        return "".join(text_parts), tool_calls

    def _parse_google_content(self, data: Mapping[str, Any]) -> tuple[str, list[JsonDict]]:
        text_parts: list[str] = []
        tool_calls: list[JsonDict] = []
        candidates = data.get("candidates") or []
        if not candidates or not isinstance(candidates[0], Mapping):
            return "", []
        content = candidates[0].get("content") or {}
        parts = content.get("parts") if isinstance(content, Mapping) else []
        for part in parts or []:
            if not isinstance(part, Mapping):
                continue
            if "text" in part:
                text_parts.append(str(part.get("text") or ""))
            function_call = part.get("functionCall")
            if isinstance(function_call, Mapping):
                tool_calls.append(
                    {
                        "type": "function",
                        "function": {
                            "name": function_call.get("name"),
                            "arguments": json.dumps(function_call.get("args") or {}),
                        },
                    }
                )
        return "".join(text_parts), tool_calls

    @asynccontextmanager
    async def _managed_client(self) -> AsyncIterator[Any]:
        client = self.client_factory()
        if inspect.isawaitable(client):
            client = await client

        if hasattr(client, "__aenter__"):
            async with client as managed:
                yield managed
            return

        try:
            yield client
        finally:
            close = getattr(client, "aclose", None)
            if close:
                result = close()
                if inspect.isawaitable(result):
                    await result

    def _bearer_headers(self, api_key: str) -> JsonDict:
        return {"authorization": f"Bearer {api_key}", "content-type": "application/json"}

    def _missing_key_payload(
        self,
        config: ProviderConfig,
        model: str,
        alias_source: str,
    ) -> JsonDict:
        return {
            "status": "disabled",
            "reason": "missing_key",
            "provider": config.provider,
            "model": model,
            "available": False,
            "enabled": False,
            "transport": config.transport,
            "network_call_made": False,
            "required_key_env": list(config.key_env),
            "alias_source": alias_source,
            "message": f"{config.provider} disabled: missing API key ({', '.join(config.key_env)}).",
        }

    def _unsupported_provider_payload(
        self,
        provider: str | None,
        model: str | None,
        alias_source: str,
    ) -> JsonDict:
        return {
            "status": "unsupported",
            "reason": "unsupported_provider",
            "provider": str(provider or "").strip().lower(),
            "model": str(model or "").strip(),
            "available": False,
            "enabled": False,
            "network_call_made": False,
            "supported_providers": sorted(PROVIDERS),
            "alias_source": alias_source,
            "message": "Unsupported provider; no external call was made.",
        }

    def _success_payload(
        self,
        config: ProviderConfig,
        model: str,
        raw: Mapping[str, Any],
        response_text: str,
        tool_calls: Sequence[Mapping[str, Any]],
        alias_source: str,
    ) -> JsonDict:
        return {
            "status": "success",
            "provider": config.provider,
            "model": model,
            "response": response_text,
            "tool_calls": list(tool_calls),
            "raw": dict(raw),
            "network_call_made": True,
            "fake_tool_success": False,
            "alias_source": alias_source,
        }

    def _error_payload(
        self,
        config: ProviderConfig,
        model: str,
        exc: Exception,
        alias_source: str,
        network_call_made: bool = True,
    ) -> JsonDict:
        provider_error = _provider_error_body(exc)
        return {
            "status": "error",
            "provider": config.provider,
            "model": model,
            "error": provider_error or str(exc),
            "provider_status_code": _http_status_code(exc),
            "provider_error": provider_error,
            "network_call_made": network_call_made,
            "fake_tool_success": False,
            "alias_source": alias_source,
        }


def _google_schema(schema: Any) -> JsonDict | None:
    if not isinstance(schema, Mapping):
        return None
    raw_type = str(schema.get("type") or "").strip().lower()
    properties = schema.get("properties")
    required = schema.get("required")
    out: JsonDict = {}
    if raw_type:
        out["type"] = raw_type
    description = schema.get("description")
    if isinstance(description, str) and description.strip():
        out["description"] = description
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        out["enum"] = [str(item) for item in enum[:100]]
    if isinstance(properties, Mapping):
        clean_properties: JsonDict = {}
        for key, value in properties.items():
            clean_value = _google_schema(value)
            if clean_value is not None:
                clean_properties[str(key)] = clean_value
        if clean_properties:
            out["properties"] = clean_properties
    items = _google_schema(schema.get("items"))
    if items is not None:
        out["items"] = items
    if isinstance(required, list) and required:
        valid_required = [
            str(item)
            for item in required
            if not out.get("properties") or str(item) in out.get("properties", {})
        ]
        if valid_required:
            out["required"] = valid_required
    if out.get("type") == "object" and not out.get("properties"):
        return None
    return out or None


def _http_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    try:
        return int(status_code) if status_code is not None else None
    except Exception:
        return None


def _provider_error_body(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        data = response.json()
        if isinstance(data, Mapping):
            error = data.get("error")
            if isinstance(error, Mapping):
                message = error.get("message") or error.get("status")
                if message:
                    return str(message)[:2000]
            return json.dumps(data, ensure_ascii=False, sort_keys=True)[:2000]
    except Exception:
        pass
    text = getattr(response, "text", "")
    if not text and callable(getattr(response, "read", None)):
        try:
            text = response.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
    return str(text or "")[:2000]
