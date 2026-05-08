# controller/agent_tools.py
# Safe local tool registry for the Ouroboros agent-machine.

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from controller.safe_shell import run_safe_shell
from controller.stream.browser_scrubber import (
    TEACHABLE_MACHINE_HOST,
    approval_matches,
    prepare_browser_ingest,
    prepare_teachablemachine_ingest,
)
from controller.stream.dreamcycle import DreamCycle
from controller.stream.metadata_11d import build_11d_metadata, missing_11d_layers
from controller.stream.normalize import normalize
from controller.stream.resonance import score as stream_resonance_score
from controller.stream.storage import _resonance_to_importance


REGISTERED_TOOLS: tuple[str, ...] = (
    "memory_search",
    "agentic_ecosystem_context",
    "browser_research",
    "brave_search",
    "ns_travel_advice",
    "chatgpt_browser_ask",
    "world_grok_ask",
    "mail_read_recent",
    "mail_send_preview",
    "mail_send",
    "social_post_preview",
    "social_post_publish",
    "codex_job_start",
    "resolve_or_build_function",
    "voice_chat_status",
    "scrub_browser_content",
    "training_ingest",
    "safe_shell",
    "prompt_understanding",
    "self_training_plan",
    "inspect_hippocampus",
    "run_tests",
    "roo_read_file",
    "roo_list_files",
    "roo_search_files",
    "roo_write_file_preview",
    "roo_write_file",
    "roo_apply_patch_preview",
    "roo_apply_patch",
    "roo_execute_command",
    "roo_attempt_completion",
    "roo_ask_followup_question",
)

DEFAULT_TEST_SELECTOR = "sandbox_tests.test_agent_tools sandbox_tests.test_self_training_loop"
SAFE_TEST_SELECTOR_RE = re.compile(r"^[A-Za-z0-9_ .:-]+$")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
WORD_RE = re.compile(r"[A-Za-z0-9_+-]{3,}")


def _tool_schema(
    name: str,
    description: str,
    properties: dict[str, dict[str, Any]],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required or []),
            },
        },
    }


AGENT_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "memory_search": _tool_schema(
        "memory_search",
        "Zoekt lokaal in Wintrip/Ouroboros ChromaDB-geheugen voordat externe bronnen worden gebruikt.",
        {
            "query": {"type": "string", "description": "Zoekvraag of doel."},
            "limit": {"type": "integer", "description": "Aantal resultaten, maximaal 12."},
        },
        ["query"],
    ),
    "agentic_ecosystem_context": _tool_schema(
        "agentic_ecosystem_context",
        "Haalt read-only agentische patrooncontext uit lokale DeepSeek en Atlas workspaces: sub-agent rollen, SDD workflow, hooks, skills en guardrails. Geen Akkoord nodig; leest geen secrets.",
        {
            "goal": {"type": "string", "description": "Gebruikersdoel of agent/workflowvraag."},
            "prefer_bridge": {"type": "boolean", "description": "Gebruik host bridge wanneer beschikbaar."},
        },
        [],
    ),
    "browser_research": _tool_schema(
        "browser_research",
        "Doet approval-gated browser/webonderzoek en voegt Brave-context toe waar beschikbaar.",
        {
            "query": {"type": "string", "description": "Onderzoeksvraag."},
            "limit": {"type": "integer", "description": "Aantal bronnen."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor externe/browseractie."},
        },
        ["query", "approval"],
    ),
    "brave_search": _tool_schema(
        "brave_search",
        "Zoekt actuele webkennis via Brave Search API en markeert de output als 11D-trainbare, untrusted-web context. Read-only; geen Akkoord nodig.",
        {
            "query": {"type": "string", "description": "Zoekvraag, liefst korter dan 400 tekens."},
            "limit": {"type": "integer", "description": "Aantal webresultaten/contextbronnen."},
            "llm_context": {"type": "boolean", "description": "Gebruik Brave LLM Context wanneer true."},
            "approval": {"type": "string", "description": "Optioneel; wordt alleen vastgelegd voor audit."},
        },
        ["query"],
    ),
    "ns_travel_advice": _tool_schema(
        "ns_travel_advice",
        "Haalt officiële NS-reisadviezen op voor Nederlandse trein/OV-vragen. Read-only; geen Akkoord nodig. Zonder NS API key geeft deze tool géén verzonnen tijden, maar een officiële plannerlink.",
        {
            "from_station": {"type": "string", "description": "Vertrekstation, naam of NS-code."},
            "to_station": {"type": "string", "description": "Aankomststation, naam of NS-code."},
            "date": {"type": "string", "description": "Optionele datum YYYY-MM-DD."},
            "time": {"type": "string", "description": "Optionele tijd HH:MM."},
            "datetime": {"type": "string", "description": "Optionele ISO datetime; heeft voorrang op date/time."},
            "search_for_arrival": {"type": "boolean", "description": "True wanneer de opgegeven tijd een gewenste aankomsttijd is."},
            "query": {"type": "string", "description": "Originele gebruikersvraag voor audit/context."},
        },
        ["from_station", "to_station"],
    ),
    "chatgpt_browser_ask": _tool_schema(
        "chatgpt_browser_ask",
        "Stelt approval-gated een vraag aan de lokale ChatGPT/browser-automatisering wanneer beschikbaar.",
        {
            "question": {"type": "string", "description": "Vraag voor ChatGPT."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor browser/app-besturing."},
        },
        ["question", "approval"],
    ),
    "world_grok_ask": _tool_schema(
        "world_grok_ask",
        "Vraagt Grok via de World Agent/browser-bridge. Vereist Akkoord voor openen/typen/submits.",
        {
            "question": {"type": "string", "description": "Vraag voor Grok."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor browser/app-besturing."},
            "open_tab": {"type": "boolean", "description": "Open een zichtbare tab wanneer mogelijk."},
            "submit": {"type": "boolean", "description": "Typ en submit de vraag wanneer toegestaan."},
        },
        ["question", "approval"],
    ),
    "mail_read_recent": _tool_schema(
        "mail_read_recent",
        "Leest recente mail read-only via de bestaande IMAP/Gmail-compatible adapter. Vereist Akkoord vanwege private data.",
        {
            "limit": {"type": "integer", "description": "Aantal recente berichten, maximaal 10."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor mailbox lezen."},
        },
        ["approval"],
    ),
    "mail_send_preview": _tool_schema(
        "mail_send_preview",
        "Maakt een mailconcept-preview zonder iets te versturen.",
        {
            "to": {"type": "string", "description": "Ontvanger(s), alleen voor preview."},
            "subject": {"type": "string", "description": "Onderwerp."},
            "body": {"type": "string", "description": "Berichttekst."},
        },
        ["to", "subject", "body"],
    ),
    "mail_send": _tool_schema(
        "mail_send",
        "Verstuurt mail alleen via een expliciet geconfigureerde send-adapter. Vereist Akkoord; claimt geen verzending zonder bewijs.",
        {
            "to": {"type": "string", "description": "Ontvanger(s)."},
            "subject": {"type": "string", "description": "Onderwerp."},
            "body": {"type": "string", "description": "Berichttekst."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor echte verzending."},
        },
        ["to", "subject", "body", "approval"],
    ),
    "social_post_preview": _tool_schema(
        "social_post_preview",
        "Maakt een social-media post preview zonder te posten.",
        {
            "platform": {"type": "string", "description": "Doelplatform, bv. x, linkedin, mastodon."},
            "content": {"type": "string", "description": "Posttekst."},
            "visibility": {"type": "string", "description": "Optionele zichtbaarheid/context."},
        },
        ["platform", "content"],
    ),
    "social_post_publish": _tool_schema(
        "social_post_publish",
        "Publiceert op social media alleen via een expliciet geconfigureerde connector. Vereist Akkoord.",
        {
            "platform": {"type": "string", "description": "Doelplatform."},
            "content": {"type": "string", "description": "Posttekst."},
            "visibility": {"type": "string", "description": "Optionele zichtbaarheid/context."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor echte publicatie."},
        },
        ["platform", "content", "approval"],
    ),
    "codex_job_start": _tool_schema(
        "codex_job_start",
        "Start een Codex agent-runtime job voor self-modification of codewerk. Vereist Akkoord.",
        {
            "task": {"type": "string", "description": "Codex taak in natuurlijke taal."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist omdat Codex bestanden kan wijzigen."},
            "timeout_seconds": {"type": "integer", "description": "Job timeout, maximaal 3600 seconden."},
        },
        ["task", "approval"],
    ),
    "resolve_or_build_function": _tool_schema(
        "resolve_or_build_function",
        "Zoekt eerst een bestaande AgentToolRegistry/ToolBridge/Codex-registry capability. Bij een missende capability gebruikt deze read-only Brave-context en mag pas na exact Akkoord Codex/Gemini en safe-shell tests starten. Geen fake success.",
        {
            "requested_capability": {"type": "string", "description": "Naam van de gezochte of te bouwen capability/tool/function."},
            "arguments": {"type": "object", "description": "JSON-argumenten voor uitvoering na succesvolle resolutie/build."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor bouwen, Gemini fallback, tests en muterende uitvoering."},
            "execute_after_build": {"type": "boolean", "description": "Voer de capability pas uit na groene tests en rediscovery."},
            "test_selector": {"type": "string", "description": "Dotted unittest selectors voor safe-shell validatie."},
            "build_task": {"type": "string", "description": "Optionele expliciete Codex/Gemini bouwopdracht."},
            "timeout_seconds": {"type": "integer", "description": "Codex timeout, maximaal 3600 seconden."},
            "wait_seconds": {"type": "integer", "description": "Optioneel aantal seconden wachten op een Codex job voordat tests starten."},
        },
        ["requested_capability"],
    ),
    "voice_chat_status": _tool_schema(
        "voice_chat_status",
        "Rapporteert de huidige spraakchat-capability zonder microfoon of audio te openen.",
        {},
        [],
    ),
    "scrub_browser_content": _tool_schema(
        "scrub_browser_content",
        "Schoont geplakte browsertekst op en maakt een veilig ingest-preview zonder meteen op te slaan.",
        {
            "text": {"type": "string", "description": "Browsertekst."},
            "url": {"type": "string", "description": "Bron-URL."},
            "approval": {"type": "string", "description": "Optionele approval voor bekende ingest-flows."},
            "title": {"type": "string", "description": "Korte titel voor de preview."},
        },
        ["text"],
    ),
    "training_ingest": _tool_schema(
        "training_ingest",
        "Slaat goedgekeurde leerstof op in de lokale 11D ChromaDB-trainingcollectie.",
        {
            "text": {"type": "string", "description": "Te leren tekst."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor opslag."},
            "target_hz": {"type": "number", "description": "Optionele resonantie-doelfrequentie."},
            "url": {"type": "string", "description": "Bron-URL of lokale bronnaam."},
            "title": {"type": "string", "description": "Korte titel."},
        },
        ["text", "approval"],
    ),
    "safe_shell": _tool_schema(
        "safe_shell",
        "Voert een safe-shell commando uit binnen de workspace allowlist. Vereist approval.",
        {
            "command": {"type": "string", "description": "Shellcommando."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
        },
        ["command", "approval"],
    ),
    "prompt_understanding": _tool_schema(
        "prompt_understanding",
        "Analyseert lokaal welke kennis, tools en approvals een prompt nodig heeft.",
        {"prompt": {"type": "string", "description": "Prompt of doel."}},
        ["prompt"],
    ),
    "self_training_plan": _tool_schema(
        "self_training_plan",
        "Maakt een veilig leerplan met memory-first en approval-gated stappen.",
        {"prompt": {"type": "string", "description": "Leerdoel of opdracht."}},
        ["prompt"],
    ),
    "inspect_hippocampus": _tool_schema(
        "inspect_hippocampus",
        "Inspecteert beperkte ChromaDB/11D-geheugenstatus en recente trainingrecords.",
        {"limit": {"type": "integer", "description": "Aantal recente records, maximaal 20."}},
        [],
    ),
    "run_tests": _tool_schema(
        "run_tests",
        "Draait Python unittest-selectors via safe shell en slaat succesvolle validatie op in 11D memory.",
        {
            "test_selector": {"type": "string", "description": "Dotted unittest selectors."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
        },
        ["test_selector", "approval"],
    ),
    "roo_read_file": _tool_schema(
        "roo_read_file",
        "Leest een workspacebestand of bekend agent-root bestand via de Roo adapter.",
        {
            "path": {"type": "string", "description": "Relatief pad of alias zoals ruflo/..., roo/... of codex/..."},
            "offset": {"type": "integer", "description": "Start byte."},
            "limit": {"type": "integer", "description": "Maximum bytes."},
        },
        ["path"],
    ),
    "roo_list_files": _tool_schema(
        "roo_list_files",
        "Geeft een begrensde bestandslijst terug via de Roo adapter.",
        {
            "path": {"type": "string", "description": "Startpad."},
            "recursive": {"type": "boolean", "description": "Recursief zoeken."},
            "limit": {"type": "integer", "description": "Maximaal aantal resultaten."},
        },
        [],
    ),
    "roo_search_files": _tool_schema(
        "roo_search_files",
        "Zoekt met regex in workspacebestanden via de Roo adapter.",
        {
            "path": {"type": "string", "description": "Startpad."},
            "regex": {"type": "string", "description": "Regex/patroon."},
            "file_pattern": {"type": "string", "description": "Optioneel bestandsfilter."},
            "limit": {"type": "integer", "description": "Maximaal aantal matches."},
        },
        ["regex"],
    ),
    "roo_write_file_preview": _tool_schema(
        "roo_write_file_preview",
        "Maakt een preview voor een bestandsschrijfactie zonder te schrijven.",
        {
            "path": {"type": "string", "description": "Doelpad."},
            "content": {"type": "string", "description": "Nieuwe inhoud."},
        },
        ["path", "content"],
    ),
    "roo_write_file": _tool_schema(
        "roo_write_file",
        "Schrijft een bestand via de Roo adapter. Vereist approval.",
        {
            "path": {"type": "string", "description": "Doelpad."},
            "content": {"type": "string", "description": "Nieuwe inhoud."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
        },
        ["path", "content", "approval"],
    ),
    "roo_apply_patch_preview": _tool_schema(
        "roo_apply_patch_preview",
        "Valideert/toont een patch zonder hem toe te passen.",
        {"patch": {"type": "string", "description": "Unified/apply_patch tekst."}},
        ["patch"],
    ),
    "roo_apply_patch": _tool_schema(
        "roo_apply_patch",
        "Past een patch toe via de Roo adapter. Vereist approval.",
        {
            "patch": {"type": "string", "description": "Unified/apply_patch tekst."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
        },
        ["patch", "approval"],
    ),
    "roo_execute_command": _tool_schema(
        "roo_execute_command",
        "Voert een begrensd commando uit via de Roo adapter. Vereist approval.",
        {
            "command": {"type": "string", "description": "Commando."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
            "timeout": {"type": "integer", "description": "Timeout in seconden."},
        },
        ["command", "approval"],
    ),
    "roo_attempt_completion": _tool_schema(
        "roo_attempt_completion",
        "Markeert een taak of mijlpaal als voltooid.",
        {
            "result": {"type": "string", "description": "Samenvatting van wat klaar is."},
            "command": {"type": "string", "description": "Optioneel verificatiecommando."},
        },
        ["result"],
    ),
    "roo_ask_followup_question": _tool_schema(
        "roo_ask_followup_question",
        "Legt een noodzakelijke vervolgvraag vast wanneer uitvoering niet veilig kan doorgaan.",
        {"question": {"type": "string", "description": "Vervolgvraag."}},
        ["question"],
    ),
}


def agent_tool_schemas(provider: str = "openai") -> list[dict[str, Any]]:
    """Return one structured schema for every registered AgentToolRegistry tool."""

    schemas = [AGENT_TOOL_SCHEMAS[name] for name in REGISTERED_TOOLS if name in AGENT_TOOL_SCHEMAS]
    if provider == "anthropic":
        return [
            {
                "name": schema["function"]["name"],
                "description": schema["function"]["description"],
                "input_schema": schema["function"]["parameters"],
            }
            for schema in schemas
        ]
    return [dict(schema) for schema in schemas]


class AgentToolRegistry:
    """Single approval-gated tool surface for UI buttons and local agents."""

    def __init__(
        self,
        kb: Any = None,
        storage: Any = None,
        app: Any = None,
        browser_researcher: Callable[..., Any] | None = None,
        chatgpt_browser: Callable[[str], Any] | None = None,
    ):
        self.kb = kb
        self.storage = storage
        self.app = app
        self.browser_researcher = browser_researcher
        self.chatgpt_browser = chatgpt_browser
        self.last_tool_result: dict[str, Any] | None = None

    def run_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        started = time.time()
        tool_name = str(tool_name or "").strip()
        try:
            if tool_name not in REGISTERED_TOOLS:
                result = _tool_result(
                    tool_name or "unknown",
                    "error",
                    stderr=f"Unknown tool: {tool_name}",
                    source="agent_tools.registry",
                    next_action=f"Choose one registered tool: {', '.join(REGISTERED_TOOLS)}",
                )
            elif tool_name == "memory_search":
                result = self.memory_search(
                    str(args.get("query") or args.get("prompt") or "Ouroboros"),
                    _int(args.get("limit"), default=5),
                )
            elif tool_name == "agentic_ecosystem_context":
                result = self.agentic_ecosystem_context(
                    str(args.get("goal") or args.get("query") or args.get("prompt") or ""),
                    prefer_bridge=bool(args.get("prefer_bridge", True)),
                )
            elif tool_name == "browser_research":
                result = self.browser_research(
                    str(args.get("query") or args.get("prompt") or ""),
                    str(args.get("approval") or ""),
                    _int(args.get("limit"), default=3),
                )
            elif tool_name == "brave_search":
                result = self.brave_search(
                    str(args.get("query") or args.get("prompt") or ""),
                    str(args.get("approval") or ""),
                    _int(args.get("limit"), default=5),
                    bool(args.get("llm_context", True)),
                )
            elif tool_name == "ns_travel_advice":
                result = self.ns_travel_advice(
                    from_station=str(args.get("from_station") or args.get("from") or ""),
                    to_station=str(args.get("to_station") or args.get("to") or ""),
                    date=str(args.get("date") or ""),
                    time_value=str(args.get("time") or ""),
                    datetime_value=str(args.get("datetime") or args.get("dateTime") or ""),
                    search_for_arrival=bool(args.get("search_for_arrival", False)),
                    query=str(args.get("query") or args.get("prompt") or ""),
                )
            elif tool_name == "chatgpt_browser_ask":
                result = self.chatgpt_browser_ask(
                    str(args.get("question") or args.get("prompt") or ""),
                    str(args.get("approval") or ""),
                )
            elif tool_name == "world_grok_ask":
                result = self.world_grok_ask(
                    str(args.get("question") or args.get("prompt") or ""),
                    str(args.get("approval") or ""),
                    open_tab=bool(args.get("open_tab", True)),
                    submit=bool(args.get("submit", True)),
                )
            elif tool_name == "mail_read_recent":
                result = self.mail_read_recent(
                    _int(args.get("limit"), default=5),
                    str(args.get("approval") or ""),
                )
            elif tool_name == "mail_send_preview":
                result = self.mail_send_preview(
                    to=str(args.get("to") or args.get("recipient") or ""),
                    subject=str(args.get("subject") or ""),
                    body=str(args.get("body") or args.get("content") or ""),
                )
            elif tool_name == "mail_send":
                result = self.mail_send(
                    to=str(args.get("to") or args.get("recipient") or ""),
                    subject=str(args.get("subject") or ""),
                    body=str(args.get("body") or args.get("content") or ""),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "social_post_preview":
                result = self.social_post_preview(
                    platform=str(args.get("platform") or ""),
                    content=str(args.get("content") or args.get("body") or ""),
                    visibility=str(args.get("visibility") or ""),
                )
            elif tool_name == "social_post_publish":
                result = self.social_post_publish(
                    platform=str(args.get("platform") or ""),
                    content=str(args.get("content") or args.get("body") or ""),
                    visibility=str(args.get("visibility") or ""),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "codex_job_start":
                result = self.codex_job_start(
                    task=str(args.get("task") or args.get("prompt") or ""),
                    approval=str(args.get("approval") or ""),
                    timeout_seconds=_int(args.get("timeout_seconds"), default=900),
                )
            elif tool_name == "resolve_or_build_function":
                result = self.resolve_or_build_function(
                    requested_capability=str(args.get("requested_capability") or args.get("capability") or args.get("tool") or ""),
                    function_args=dict(args.get("arguments") or args.get("function_args") or {}),
                    approval=str(args.get("approval") or ""),
                    execute_after_build=bool(args.get("execute_after_build", False)),
                    test_selector=str(args.get("test_selector") or ""),
                    build_task=str(args.get("build_task") or ""),
                    timeout_seconds=_int(args.get("timeout_seconds"), default=900),
                    wait_seconds=_int(args.get("wait_seconds"), default=0),
                )
            elif tool_name == "voice_chat_status":
                result = self.voice_chat_status()
            elif tool_name == "scrub_browser_content":
                result = self.scrub_browser_content(
                    text=str(args.get("text") or args.get("browser_text") or ""),
                    url=str(args.get("url") or f"https://{TEACHABLE_MACHINE_HOST}/train"),
                    approval=str(args.get("approval") or ""),
                    title=str(args.get("title") or "Agent Tool browser scrub"),
                )
            elif tool_name == "training_ingest":
                result = self.training_ingest(
                    text=str(args.get("text") or args.get("browser_text") or ""),
                    approval=str(args.get("approval") or ""),
                    target_hz=_float_or_none(args.get("target_hz")),
                    url=str(args.get("url") or f"https://{TEACHABLE_MACHINE_HOST}/train"),
                    title=str(args.get("title") or "Agent Tool training ingest"),
                )
            elif tool_name == "safe_shell":
                result = self.safe_shell(
                    str(args.get("command") or ""),
                    str(args.get("approval") or ""),
                )
            elif tool_name == "prompt_understanding":
                result = self.prompt_understanding(str(args.get("prompt") or args.get("text") or ""))
            elif tool_name == "self_training_plan":
                result = self.self_training_plan(str(args.get("prompt") or args.get("text") or ""))
            elif tool_name == "inspect_hippocampus":
                result = self.inspect_hippocampus(_int(args.get("limit"), default=6))
            elif tool_name == "run_tests":
                result = self.run_tests(
                    str(args.get("test_selector") or DEFAULT_TEST_SELECTOR),
                    str(args.get("approval") or ""),
                )
            elif tool_name.startswith("roo_"):
                result = self.roo_tool(tool_name, args)
            else:
                result = _tool_result(tool_name, "error", stderr="Registry dispatch invariant failed.")
        except Exception as exc:
            result = _tool_result(
                tool_name or "unknown",
                "error",
                stderr=str(exc),
                source="agent_tools.exception",
                next_action="Inspect stderr and retry with a smaller, explicit request.",
            )

        result["duration_seconds"] = round(time.time() - started, 3)
        result.setdefault("autonomy", self._autonomy_for(result))
        self.last_tool_result = result
        return result

    def status(self) -> dict[str, Any]:
        return {
            "status": "online",
            "available_tools": list(REGISTERED_TOOLS),
            "last_tool_result": self.last_tool_result,
            "roo_adapter": self._roo_status(),
            "autonomy": self._autonomy_for(self.last_tool_result or {}),
        }

    def get_tool_schemas(self, provider: str = "openai") -> list[dict[str, Any]]:
        """Return function calling schemas for registered tools."""

        return agent_tool_schemas(provider=provider)

    def _to_anthropic_schema(self, openai_schema: dict[str, Any]) -> dict[str, Any]:
        fn = openai_schema.get("function", {})
        return {
            "name": fn.get("name"),
            "description": fn.get("description"),
            "input_schema": fn.get("parameters")
        }

    def memory_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        limit = max(1, min(int(limit), 12))
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        if self.kb is not None:
            try:
                for found in self.kb.search(query, n_results=limit):
                    items.append(
                        {
                            "source": "wintrip_knowledge",
                            "text": str(found.get("text", ""))[:900],
                            "metadata": found.get("metadata", {}),
                            "tier": found.get("tier", "unknown"),
                        }
                    )
            except Exception as exc:
                errors.append(f"wintrip_knowledge: {exc}")

        training_items, training_errors = _rank_training_records(query, limit=limit)
        items.extend(training_items)
        errors.extend(training_errors)
        payload = {
            "query": query,
            "matches": items[:limit],
            "count": len(items[:limit]),
            "errors": errors,
        }
        return _tool_result(
            "memory_search",
            "success",
            result=payload,
            stdout=json.dumps(payload, ensure_ascii=False, indent=2),
            source="hippocampus",
            next_action="Use matching memory as context, or request browser_research when knowledge is missing.",
        )

    def agentic_ecosystem_context(self, goal: str, *, prefer_bridge: bool = True) -> dict[str, Any]:
        try:
            from controller.agentic_ecosystem import agentic_ecosystem_context

            payload = agentic_ecosystem_context(goal, prefer_bridge=prefer_bridge)
        except Exception as exc:
            return _tool_result(
                "agentic_ecosystem_context",
                "error",
                stderr=str(exc),
                source="agentic_ecosystem",
                next_action="Controleer WINTRIP_DEEPSEEK_PATH/WINTRIP_ATLAS_PATH of host bridge status.",
            )
        status = str(payload.get("status") or "unknown")
        stdout = _agentic_ecosystem_stdout(payload)
        return _tool_result(
            "agentic_ecosystem_context",
            "success" if status in {"online", "missing"} else status,
            result=payload,
            stdout=stdout,
            source="agentic_ecosystem",
            approval_status="not_required_readonly",
            metadata_11d={
                "dimension_count": 11,
                "source_type": "local_agentic_ecosystem",
                "sources": ",".join(payload.get("sources") or []),
                "taint": "local_readonly_docs",
            },
            next_action="Gebruik deze patronen om rollen, handoffs, guardrails en cockpit-provenance concreet te maken.",
        )

    def browser_research(self, query: str, approval: str, limit: int = 3) -> dict[str, Any]:
        if not query.strip():
            return _tool_result(
                "browser_research",
                "error",
                stderr="Research query is empty.",
                source="browser_research",
                next_action="Provide a concrete query.",
            )
        if not approval_matches(approval):
            return _tool_result(
                "browser_research",
                "blocked",
                result={"query": query, "approval_required": True},
                source="browser_research",
                approval_status="pending_philip_akkoord",
                next_action="Ask Philip for Akkoord before external browser research.",
            )

        try:
            if self.browser_researcher is not None:
                try:
                    raw = self.browser_researcher(query, approval=approval)
                except TypeError:
                    raw = self.browser_researcher(query, max_results=max(1, min(limit, 10)))
            else:
                from controller.browser_research import browser_research as run_browser_research

                raw = run_browser_research(query=query, approval=approval, include_brave=False)
        except Exception as exc:
            return _tool_result(
                "browser_research",
                "error",
                stderr=str(exc),
                source="browser_research",
                approval_status="approved",
                next_action="Retry later or use manual browser_text with scrub_browser_content.",
            )

        brave = _brave_companion_for_browser_research(query, approval=approval, limit=limit)
        if isinstance(raw, dict):
            raw = dict(raw)
            raw["brave"] = brave

        stdout = _stringify(raw)
        raw_status = raw.get("status") if isinstance(raw, dict) else None
        if raw_status in {"success", "preview", "approved"}:
            status = "success"
        elif raw_status in {"blocked", "approval_required", "unavailable", "failed"}:
            status = raw_status
        else:
            status = "error" if "[WEB SEARCH FOUT]" in stdout or stdout.lower().startswith("error") else "success"
        return _tool_result(
            "browser_research",
            status,
            result={"query": query, "response": raw, "brave": brave, "stored": False},
            stdout=stdout,
            stderr="" if status == "success" else stdout,
            source="browser_research",
            approval_status=(raw.get("approval_status") if isinstance(raw, dict) else "approved") or "approved",
            stored_to_memory=False,
            metadata_11d={},
            next_action="Review Brave/browser context; use training_ingest with Akkoord for durable 11D storage.",
        )

    def brave_search(self, query: str, approval: str, limit: int = 5, llm_context: bool = True) -> dict[str, Any]:
        if not query.strip():
            return _tool_result(
                "brave_search",
                "error",
                stderr="Brave query is empty.",
                source="brave_search",
                next_action="Provide a concrete query.",
            )
        try:
            from controller.brave_search import search_brave_llm_context, search_brave_web

            if llm_context:
                raw = search_brave_llm_context(query, maximum_number_of_urls=max(1, min(limit, 20)))
            else:
                raw = search_brave_web(query, count=max(1, min(limit, 20)))
        except Exception as exc:
            return _tool_result(
                "brave_search",
                "error",
                stderr=str(exc),
                source="brave_search",
                approval_status="approved",
                next_action="Check Brave key status and retry with a smaller query.",
            )

        status = str(raw.get("status") or "unknown") if isinstance(raw, dict) else "error"
        stdout = _stringify(raw)
        if status == "missing_api_key":
            next_action = "Configure BRAVE_SEARCH_API_KEY or save provider=brave in cockpit API Keys."
        elif status == "rate_limited":
            next_action = "Wait for Brave X-RateLimit-Reset and retry."
        else:
            next_action = "Use training_ingest/knowledge accelerator to store durable Brave context in 11D memory."
        return _tool_result(
            "brave_search",
            "success" if status == "success" else status,
            result={"query": query, "response": raw, "stored": False},
            stdout=stdout,
            stderr="" if status == "success" else stdout,
            source="brave_search",
            approval_status="approved" if approval_matches(approval) else "not_required_readonly",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "brave_search", "taint": "untrusted_web"},
            next_action=next_action,
        )

    def ns_travel_advice(
        self,
        *,
        from_station: str,
        to_station: str,
        date: str = "",
        time_value: str = "",
        datetime_value: str = "",
        search_for_arrival: bool = False,
        query: str = "",
    ) -> dict[str, Any]:
        from_station = " ".join(str(from_station or "").split())
        to_station = " ".join(str(to_station or "").split())
        if not from_station or not to_station:
            return _tool_result(
                "ns_travel_advice",
                "error",
                result={"from_station": from_station, "to_station": to_station, "query": query},
                stderr="Vertrek- en aankomststation zijn nodig voor NS-reisadvies.",
                source="ns_travel_advice",
                next_action="Vraag om vertrekstation en aankomststation, of gebruik de NS Reisplanner handmatig.",
            )

        date_time = _ns_datetime(date=date, time_value=time_value, datetime_value=datetime_value)
        planner_url = _ns_planner_url(from_station, to_station, date_time=date_time, search_for_arrival=search_for_arrival)
        key = _ns_api_key()
        base_payload = {
            "from_station": from_station,
            "to_station": to_station,
            "date": date,
            "time": time_value,
            "datetime": date_time,
            "search_for_arrival": bool(search_for_arrival),
            "query": query,
            "planner_url": planner_url,
            "authoritative": False,
            "source": "NS Reisplanner / NS API",
        }
        if not key:
            stdout = (
                "NS API key ontbreekt. Er zijn geen officiële treintijden opgehaald en ik mag geen tijden uit Brave/snippets afleiden.\n"
                f"Open de officiële NS Reisplanner: {planner_url}\n"
                "Configureer WINTRIP_NS_API_KEY, NS_API_KEY, NS_APP_API_KEY of NS_API_SUBSCRIPTION_KEY voor live reisadviezen."
            )
            return _tool_result(
                "ns_travel_advice",
                "preview",
                result={**base_payload, "configured": False, "missing_api_key": True},
                stdout=stdout,
                source="ns_travel_advice",
                approval_status="not_required_readonly",
                metadata_11d={"dimension_count": 11, "source_type": "ns_travel_advice", "taint": "official_missing_key"},
                next_action="Configureer een NS API key of open de officiële plannerlink; noem geen exacte tijden zonder officiële data.",
            )

        params = {
            "fromStation": from_station,
            "toStation": to_station,
            "searchForArrival": "true" if search_for_arrival else "false",
        }
        if date_time:
            params["dateTime"] = date_time
        url = "https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3/trips?" + urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Ocp-Apim-Subscription-Key": key,
                "User-Agent": "WintripAI-Ouroboros/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=float(os.getenv("WINTRIP_NS_API_TIMEOUT", "8"))) as response:
                raw_text = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1200] if exc.fp else str(exc)
            return _tool_result(
                "ns_travel_advice",
                "error",
                result={**base_payload, "configured": True, "http_status": exc.code, "planner_url": planner_url},
                stderr=f"NS API HTTP {exc.code}: {detail}",
                source="ns_travel_advice",
                approval_status="not_required_readonly",
                metadata_11d={"dimension_count": 11, "source_type": "ns_travel_advice", "taint": "official_api_error"},
                next_action="Controleer de NS API key/stationsnamen of open de officiële plannerlink.",
            )
        except Exception as exc:
            return _tool_result(
                "ns_travel_advice",
                "error",
                result={**base_payload, "configured": True, "planner_url": planner_url},
                stderr=str(exc),
                source="ns_travel_advice",
                approval_status="not_required_readonly",
                metadata_11d={"dimension_count": 11, "source_type": "ns_travel_advice", "taint": "official_api_error"},
                next_action="Retry of open de officiële NS Reisplannerlink.",
            )

        try:
            raw = json.loads(raw_text)
        except Exception as exc:
            return _tool_result(
                "ns_travel_advice",
                "error",
                result={**base_payload, "configured": True, "raw_preview": raw_text[:1200]},
                stderr=f"NS API gaf geen JSON: {exc}",
                source="ns_travel_advice",
                approval_status="not_required_readonly",
                metadata_11d={"dimension_count": 11, "source_type": "ns_travel_advice", "taint": "official_parse_error"},
                next_action="Open de officiële plannerlink en controleer de NS API response.",
            )

        summary = _summarize_ns_trips(raw)
        payload = {**base_payload, "configured": True, "authoritative": True, "advice": summary, "raw": raw}
        stdout = json.dumps(
            {
                "source": "official_ns_api",
                "authoritative": True,
                "from_station": from_station,
                "to_station": to_station,
                "datetime": date_time,
                "search_for_arrival": bool(search_for_arrival),
                "planner_url": planner_url,
                "advice": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
        return _tool_result(
            "ns_travel_advice",
            "success",
            result=payload,
            stdout=stdout,
            source="ns_travel_advice",
            approval_status="not_required_readonly",
            metadata_11d={"dimension_count": 11, "source_type": "ns_travel_advice", "taint": "official_ns_api"},
            next_action="Gebruik alleen deze officiële NS API-output voor exacte vertrek- en aankomsttijden.",
        )

    def chatgpt_browser_ask(self, question: str, approval: str) -> dict[str, Any]:
        if not question.strip():
            return _tool_result(
                "chatgpt_browser_ask",
                "error",
                stderr="Question is empty.",
                source="chatgpt_browser",
                next_action="Provide a concrete question.",
            )
        if not approval_matches(approval):
            return _tool_result(
                "chatgpt_browser_ask",
                "blocked",
                result={"question": question, "approval_required": True},
                source="chatgpt_browser",
                approval_status="pending_philip_akkoord",
                next_action="Ask Philip for Akkoord before controlling the ChatGPT browser/app.",
            )

        try:
            if self.chatgpt_browser is not None:
                try:
                    raw = self.chatgpt_browser(question, approval=approval)
                except TypeError:
                    raw = self.chatgpt_browser(question)
            else:
                from controller.browser_research import chatgpt_browser_ask as run_chatgpt_browser_ask

                raw = run_chatgpt_browser_ask(question=question, approval=approval)
        except Exception as exc:
            return _tool_result(
                "chatgpt_browser_ask",
                "error",
                stderr=str(exc),
                source="chatgpt_browser",
                approval_status="approved",
                next_action="Inspect OS/browser availability and retry after Philip approves.",
            )

        stdout = _stringify(raw)
        raw_status = raw.get("status") if isinstance(raw, dict) else None
        if raw_status in {"success", "preview", "approved"}:
            status = "success"
        elif raw_status in {"blocked", "approval_required", "unavailable", "failed"}:
            status = raw_status
        else:
            status = "error" if _looks_like_failure(stdout) else "success"
        return _tool_result(
            "chatgpt_browser_ask",
            status,
            result={"question": question, "response": raw, "stored": False},
            stdout=stdout,
            stderr="" if status == "success" else stdout,
            source="chatgpt_browser",
            approval_status=(raw.get("approval_status") if isinstance(raw, dict) else "approved") or "approved",
            stored_to_memory=False,
            metadata_11d={},
            next_action="Reflect on the answer; store durable knowledge only via training_ingest after review.",
        )

    def world_grok_ask(self, question: str, approval: str, *, open_tab: bool = True, submit: bool = True) -> dict[str, Any]:
        if not question.strip():
            return _tool_result(
                "world_grok_ask",
                "error",
                stderr="Question is empty.",
                source="world_agent:grok",
                next_action="Provide a concrete Grok question.",
            )
        if not approval_matches(approval):
            return _tool_result(
                "world_grok_ask",
                "blocked",
                result={"question": question, "approval_required": True, "blocked_actions": ["open_tab", "type", "submit"]},
                source="world_agent:grok",
                approval_status="pending_philip_akkoord",
                next_action="Ask Philip for Akkoord before controlling Grok/browser automation.",
            )

        try:
            from controller.world_agent import ask_grok_via_world_agent

            raw = ask_grok_via_world_agent(question, approval=approval, open_tab=open_tab, submit=submit)
        except Exception as exc:
            return _tool_result(
                "world_grok_ask",
                "error",
                stderr=str(exc),
                source="world_agent:grok",
                approval_status="approved",
                next_action="Inspect World Agent/browser bridge status before retrying.",
            )

        raw = raw if isinstance(raw, dict) else {"status": "success", "response": str(raw)}
        status = str(raw.get("status") or "unknown")
        if status == "approval_required":
            status = "blocked"
        stored = bool(((raw.get("memory") if isinstance(raw.get("memory"), dict) else {}) or {}).get("stored"))
        return _tool_result(
            "world_grok_ask",
            status,
            result={"question": question, "response": raw, "stored": stored},
            stdout=_stringify(raw),
            stderr="" if status in {"success", "opened", "login_required", "rate_limited"} else _stringify(raw),
            source="world_agent:grok",
            approval_status="approved",
            stored_to_memory=stored,
            metadata_11d={"dimension_count": 11, "source_type": "world_agent_grok", "taint": "untrusted_browser"},
            next_action="Use the Grok answer as untrusted context; store durable learning only after review.",
        )

    def mail_read_recent(self, limit: int, approval: str) -> dict[str, Any]:
        if not approval_matches(approval):
            return _tool_result(
                "mail_read_recent",
                "blocked",
                result={"approval_required": True, "read_only": True},
                source="mail:imap_readonly",
                approval_status="pending_philip_akkoord",
                next_action="Ask Philip for Akkoord before reading private mailbox data.",
            )
        limit = max(1, min(int(limit or 5), 10))
        try:
            from controller.mail_fetcher import fetch_recent_emails

            raw = fetch_recent_emails(limit=limit)
        except Exception as exc:
            return _tool_result(
                "mail_read_recent",
                "error",
                stderr=str(exc),
                source="mail:imap_readonly",
                approval_status="approved",
                next_action="Check IMAP/Gmail configuration without exposing credentials.",
            )

        messages = [_compact_mail_item(item) for item in (raw if isinstance(raw, list) else [raw])]
        error_items = [item for item in messages if str(item.get("status") or "").lower() == "error"]
        payload = {"count": len(messages), "messages": messages, "read_only": True}
        return _tool_result(
            "mail_read_recent",
            "error" if error_items else "success",
            result=payload,
            stdout=_stringify(payload),
            stderr=_stringify(error_items) if error_items else "",
            source="mail:imap_readonly",
            approval_status="approved",
            metadata_11d={"dimension_count": 11, "source_type": "private_mail_readonly", "taint": "private_user_data"},
            next_action="Summarize or draft a reply; mail_send still requires Akkoord and a configured send adapter.",
        )

    def mail_send_preview(self, to: str, subject: str, body: str) -> dict[str, Any]:
        missing = [name for name, value in {"to": to, "subject": subject, "body": body}.items() if not str(value or "").strip()]
        if missing:
            return _tool_result(
                "mail_send_preview",
                "error",
                stderr=f"Missing fields for mail preview: {', '.join(missing)}.",
                source="mail:preview",
                next_action="Provide to, subject and body.",
            )
        payload = {
            "to": _redact_operational_text(to)[:500],
            "subject": _redact_operational_text(subject)[:300],
            "body_preview": _redact_operational_text(body)[:2000],
            "sent": False,
            "preview_only": True,
        }
        return _tool_result(
            "mail_send_preview",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="mail:preview",
            approval_status="not_required_preview",
            next_action="Review the draft; use mail_send with exact Akkoord only when Philip wants to send.",
        )

    def mail_send(self, to: str, subject: str, body: str, approval: str) -> dict[str, Any]:
        if not approval_matches(approval):
            return _tool_result(
                "mail_send",
                "blocked",
                result={"approval_required": True, "sent": False},
                source="mail:send",
                approval_status="pending_philip_akkoord",
                next_action="Ask Philip for Akkoord before sending mail.",
            )
        preview = self.mail_send_preview(to=to, subject=subject, body=body)
        if preview.get("status") != "success":
            preview["tool_name"] = "mail_send"
            preview["approval_status"] = "approved"
            return preview
        return _tool_result(
            "mail_send",
            "unavailable",
            result={**preview["result"], "sent": False, "send_adapter_configured": False},
            stdout="Mail send is approval-approved but no SMTP/Gmail send adapter is configured in Agentic Core.",
            stderr="No mail send adapter configured; no mail was sent.",
            source="mail:send",
            approval_status="approved",
            next_action="Configure a send connector, or keep this as a draft/preview.",
        )

    def social_post_preview(self, platform: str, content: str, visibility: str = "") -> dict[str, Any]:
        platform = str(platform or "").strip().lower()
        content = str(content or "").strip()
        if not platform or not content:
            return _tool_result(
                "social_post_preview",
                "error",
                stderr="Platform and content are required for a social post preview.",
                source="social:preview",
                next_action="Provide platform and content.",
            )
        payload = {
            "platform": platform[:80],
            "content_preview": _redact_operational_text(content)[:2000],
            "visibility": str(visibility or "")[:120],
            "posted": False,
            "preview_only": True,
        }
        return _tool_result(
            "social_post_preview",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="social:preview",
            approval_status="not_required_preview",
            next_action="Review the post; social_post_publish requires Akkoord and a configured connector.",
        )

    def social_post_publish(self, platform: str, content: str, visibility: str, approval: str) -> dict[str, Any]:
        if not approval_matches(approval):
            return _tool_result(
                "social_post_publish",
                "blocked",
                result={"approval_required": True, "posted": False},
                source="social:publish",
                approval_status="pending_philip_akkoord",
                next_action="Ask Philip for Akkoord before posting on social media.",
            )
        preview = self.social_post_preview(platform=platform, content=content, visibility=visibility)
        if preview.get("status") != "success":
            preview["tool_name"] = "social_post_publish"
            preview["approval_status"] = "approved"
            return preview
        return _tool_result(
            "social_post_publish",
            "unavailable",
            result={**preview["result"], "posted": False, "connector_configured": False},
            stdout="Social publish is approval-approved but no social connector is configured in Agentic Core.",
            stderr="No social connector configured; no post was published.",
            source="social:publish",
            approval_status="approved",
            next_action="Configure a platform connector, or keep this as a preview.",
        )

    def codex_job_start(self, task: str, approval: str, timeout_seconds: int = 900) -> dict[str, Any]:
        if not str(task or "").strip():
            return _tool_result(
                "codex_job_start",
                "error",
                stderr="Codex task is empty.",
                source="agent_runtime:codex",
                next_action="Provide a concrete self-modification/code task.",
            )
        if not approval_matches(approval):
            return _tool_result(
                "codex_job_start",
                "blocked",
                result={"approval_required": True, "job_started": False},
                source="agent_runtime:codex",
                approval_status="pending_philip_akkoord",
                next_action="Ask Philip for Akkoord before starting a Codex job that may edit files.",
            )
        try:
            from controller.agent_runtime.orchestrator import get_orchestrator

            job = get_orchestrator().submit(
                "codex",
                task,
                timeout_seconds=max(1, min(int(timeout_seconds or 900), 3600)),
                metadata={"source": "agentic_core", "approval_status": "approved"},
            )
        except Exception as exc:
            return _tool_result(
                "codex_job_start",
                "error",
                stderr=str(exc),
                source="agent_runtime:codex",
                approval_status="approved",
                next_action="Inspect Codex binary/auth/host bridge status.",
            )
        job_payload = job.to_dict() if callable(getattr(job, "to_dict", None)) else dict(job)
        return _tool_result(
            "codex_job_start",
            "success",
            result={"job_started": True, "job": job_payload},
            stdout=f"Codex job started: {job_payload.get('job_id')}",
            source="agent_runtime:codex",
            approval_status="approved",
            metadata_11d={"dimension_count": 11, "source_type": "codex_self_modification_job"},
            next_action="Watch Agent Jobs events and review changed files/tests before trusting the result.",
        )

    def resolve_or_build_function(
        self,
        requested_capability: str,
        function_args: dict[str, Any] | None = None,
        approval: str = "",
        execute_after_build: bool = False,
        test_selector: str = "",
        build_task: str = "",
        timeout_seconds: int = 900,
        wait_seconds: int = 0,
    ) -> dict[str, Any]:
        from controller.self_programming_loop import DEFAULT_BUILD_TEST_SELECTOR, resolve_or_build_function

        payload = resolve_or_build_function(
            requested_capability=requested_capability,
            function_args=dict(function_args or {}),
            approval=approval,
            execute_after_build=execute_after_build,
            test_selector=test_selector or DEFAULT_BUILD_TEST_SELECTOR,
            build_task=build_task,
            timeout_seconds=timeout_seconds,
            wait_seconds=wait_seconds,
            agent_registry=self,
        )
        status = str(payload.get("status") or "error")
        stderr = ""
        if status not in {"success", "preview", "stored", "completed", "opened", "running", "queued"}:
            stderr = str(payload.get("reason") or payload.get("next_action") or status)
        return _tool_result(
            "resolve_or_build_function",
            status,
            result=payload,
            stdout=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            stderr=stderr,
            source="self_programming_loop",
            approval_status=str(payload.get("approval_status") or ("approved" if approval == "Akkoord" else "not_required_for_resolution")),
            stored_to_memory=False,
            metadata_11d={
                "dimension_count": 11,
                "source_type": "self_programming_loop",
                "requested_capability": str(requested_capability or "")[:200],
                "phase": str(payload.get("phase") or ""),
            },
            next_action=str(payload.get("next_action") or "Review discovery/build/tests before trusting or executing the capability."),
        )

    def voice_chat_status(self) -> dict[str, Any]:
        payload = {
            "status": "not_configured",
            "input": {"microphone": False, "speech_to_text": False},
            "output": {"text_to_speech": False},
            "pocket_voice": "available_for_text_chat",
            "route": "status_only",
            "fake_success": False,
        }
        return _tool_result(
            "voice_chat_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="voice:status",
            next_action="Add STT/TTS adapters after Agentic Core provenance is stable.",
        )

    def scrub_browser_content(self, text: str, url: str, approval: str = "", title: str = "Browser scrub") -> dict[str, Any]:
        if not text.strip():
            return _tool_result(
                "scrub_browser_content",
                "error",
                stderr="Browser text is empty.",
                source=url,
                next_action="Provide browser_text to scrub.",
            )
        parsed = urlparse(url)
        try:
            if (parsed.hostname or "").lower() == TEACHABLE_MACHINE_HOST:
                scrubbed = prepare_teachablemachine_ingest(url=url, browser_text=text, approval=approval, title=title)
            else:
                scrubbed = prepare_browser_ingest(url=url, browser_text=text, approval=approval, title=title)
        except Exception as exc:
            return _tool_result(
                "scrub_browser_content",
                "error",
                stderr=str(exc),
                source=url,
                next_action="Use a valid http(s) URL and bounded browser text.",
            )

        payload = {
            "source_url": scrubbed.source_url,
            "source_host": scrubbed.source_host,
            "taint": scrubbed.taint,
            "approval_status": scrubbed.approval_status,
            "requires_approval": scrubbed.requires_approval,
            "blocked_patterns": list(scrubbed.blocked_patterns),
            "allowed_actions": list(scrubbed.allowed_actions),
            "blocked_actions": list(scrubbed.blocked_actions),
            "diff_hash": scrubbed.diff_hash,
            "diff_view": scrubbed.diff_view,
            "scrubbed_text": scrubbed.scrubbed_text,
        }
        return _tool_result(
            "scrub_browser_content",
            "success",
            result=payload,
            stdout=scrubbed.scrubbed_text,
            source=scrubbed.source_url,
            approval_status=scrubbed.approval_status,
            next_action="Review diff_view; use training_ingest with Akkoord to store approved learning.",
        )

    def training_ingest(
        self,
        text: str,
        approval: str,
        target_hz: float | None,
        url: str,
        title: str,
    ) -> dict[str, Any]:
        if not text.strip():
            return _tool_result(
                "training_ingest",
                "error",
                stderr="Training text is empty.",
                source=url,
                next_action="Provide text or browser_text.",
            )

        payload = _preview_payload_local(
            url=url,
            browser_text=text,
            title=title,
            target_hz=target_hz,
            approval=approval or None,
            request=self._request(),
        )
        if payload["approval_status"] != "approved":
            _remember_event_local(self._request(), "agent_training_ingest_pending", payload)
            return _tool_result(
                "training_ingest",
                "blocked",
                result={
                    "approval_required": True,
                    "approval_status": payload["approval_status"],
                    "diff_view": payload["diff_view"],
                    "blocked_patterns": payload["blocked_patterns"],
                    "metadata_11d": payload["metadata_11d"],
                    "pipeline": payload["pipeline"],
                },
                stdout="Training ingest preview ready; storage waits for Philip Akkoord.",
                source=payload["source_url"],
                approval_status=payload["approval_status"],
                metadata_11d=payload["metadata_11d"],
                next_action="Philip reviews diff_view and says Akkoord to store in 11D ChromaDB.",
            )

        stored, metadata_11d, item_id, reason = self._store_learning_action(
            tool_name="training_ingest",
            document=payload["scrubbed_text"],
            approval_status="approved",
            source=payload["source_url"],
            source_type="url",
            metadata_11d=payload["metadata_11d"],
            extra_metadata={
                "source_host": payload["source_host"],
                "taint": payload["taint"],
                "diff_hash": payload["diff_hash"],
                "resonance_score": float(payload["resonance"]["score"]),
                "dream_hz": float(payload["dreamcycle"]["dream_hz"]),
                "frequency_band": payload["dreamcycle"]["frequency_band"],
            },
        )
        payload.update(
            {
                "stored": stored,
                "item_id": item_id,
                "storage_target": "wintrip_training_11d" if stored else "unavailable",
                "reason": reason,
                "collection_count": _safe_total_count(self.storage) if self.storage is not None else 0,
            }
        )
        _remember_event_local(self._request(), "agent_training_ingest_stored" if stored else "agent_training_ingest_failed", payload)
        return _tool_result(
            "training_ingest",
            "success" if stored else "error",
            result={
                "item_id": item_id,
                "reason": reason,
                "stored": stored,
                "storage_target": payload["storage_target"],
                "collection_count": payload["collection_count"],
                "dreamcycle": payload["dreamcycle"],
                "metadata_11d": metadata_11d,
            },
            stdout=reason,
            stderr="" if stored else reason,
            source=payload["source_url"],
            approval_status="approved",
            stored_to_memory=stored,
            metadata_11d=metadata_11d,
            next_action="Reflect on the stored learning and run tests when this changed behavior.",
        )

    def safe_shell(self, command: str, approval: str) -> dict[str, Any]:
        coherence = _coherence_metadata("safe_shell", command)
        result = run_safe_shell(command, approval=approval)
        approval_status = "approved" if result.get("approved") else "pending_philip_akkoord"
        return _tool_result(
            "safe_shell",
            result.get("status", "error"),
            result={"command": command, "exit_code": result.get("exit_code"), "workspace": result.get("workspace")},
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", "") or (result.get("reason") if result.get("status") != "success" else ""),
            source="safe_shell",
            approval_status=approval_status,
            metadata_11d=coherence,
            next_action="Review stdout/stderr; store learning with training_ingest if it is durable knowledge.",
        )

    def prompt_understanding(self, prompt: str) -> dict[str, Any]:
        understanding = understand_prompt(prompt)
        return _tool_result(
            "prompt_understanding",
            "success" if prompt.strip() else "error",
            result=understanding,
            stdout=json.dumps(understanding, ensure_ascii=False, indent=2),
            stderr="" if prompt.strip() else "Prompt is empty.",
            source="prompt_understanding",
            next_action=understanding["next_action"],
        )

    def self_training_plan(self, prompt: str) -> dict[str, Any]:
        from controller.self_training import build_self_training_plan

        understanding = understand_prompt(prompt)
        plan = build_self_training_plan(prompt, understanding=understanding)
        return _tool_result(
            "self_training_plan",
            "success" if prompt.strip() else "error",
            result=plan,
            stdout=json.dumps(plan, ensure_ascii=False, indent=2),
            stderr="" if prompt.strip() else "Prompt is empty.",
            source="self_training",
            next_action=plan["next_action"],
        )

    def inspect_hippocampus(self, limit: int = 6) -> dict[str, Any]:
        limit = max(1, min(int(limit), 20))
        errors: list[str] = []
        training_count = 0
        training_records = {"ids": [], "metadatas": [], "documents": []}
        try:
            training = _training_collection()
            training_count = int(training.count())
            training_records = training.get(limit=limit, include=["documents", "metadatas"])
        except Exception as exc:
            errors.append(f"wintrip_training_11d: {exc}")

        main_count = 0
        if self.kb is not None:
            try:
                main_count = int(self.kb.collection.count())
            except Exception as exc:
                errors.append(f"wintrip_knowledge: {exc}")

        payload = {
            "main_collection_count": main_count,
            "training_collection_count": training_count,
            "recent_training_ids": training_records.get("ids", []),
            "recent_training_metadatas": training_records.get("metadatas", []),
            "recent_training_documents": [str(doc)[:500] for doc in training_records.get("documents", [])],
            "errors": errors,
        }
        return _tool_result(
            "inspect_hippocampus",
            "success",
            result=payload,
            stdout=json.dumps(payload, ensure_ascii=False, indent=2),
            source="hippocampus",
            next_action="Use memory_search for targeted retrieval or training_ingest for approved learning.",
        )

    def run_tests(self, test_selector: str, approval: str) -> dict[str, Any]:
        selector = " ".join(str(test_selector or DEFAULT_TEST_SELECTOR).split())
        coherence = _coherence_metadata("run_tests", selector)
        if not SAFE_TEST_SELECTOR_RE.match(selector):
            return _tool_result(
                "run_tests",
                "error",
                stderr="Test selector contains blocked characters.",
                source="python_unittest",
                metadata_11d=coherence,
                next_action="Use dotted unittest module names only.",
            )
        shell = run_safe_shell(f"python3 -m unittest {selector}", approval=approval)
        approval_status = "approved" if shell.get("approved") else "pending_philip_akkoord"
        status = shell.get("status", "error")
        stored = False
        metadata_11d: dict[str, Any] = {}
        if status == "success":
            stored, metadata_11d, _item_id, _reason = self._store_learning_action(
                tool_name="run_tests",
                document=f"Tests OK: {selector}\n\n{shell.get('stdout', '')[-3000:]}",
                approval_status="approved",
                source="python_unittest",
                source_type="manual",
            )
        metadata_11d = {**metadata_11d, **coherence}
        return _tool_result(
            "run_tests",
            status,
            result={
                "test_selector": selector,
                "exit_code": shell.get("exit_code"),
                "workspace": shell.get("workspace"),
                "stored": stored,
            },
            stdout=shell.get("stdout", ""),
            stderr=shell.get("stderr", "") or (shell.get("reason") if status != "success" else ""),
            source="python_unittest",
            approval_status=approval_status,
            stored_to_memory=stored,
            metadata_11d=metadata_11d,
            next_action="Fix failing tests or reflect on the passing validation.",
        )

    def roo_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        from controller import roo_tools

        if tool_name == "roo_read_file":
            return roo_tools.read_file(
                path=str(args.get("path") or ""),
                offset=_int_or_none(args.get("offset")),
                limit=_int_or_none(args.get("limit")),
            )
        if tool_name == "roo_list_files":
            return roo_tools.list_files(
                path=str(args.get("path") or "."),
                recursive=bool(args.get("recursive")),
                limit=_int(args.get("limit"), default=200),
            )
        if tool_name == "roo_search_files":
            return roo_tools.search_files(
                path=str(args.get("path") or "."),
                regex=str(args.get("regex") or args.get("pattern") or ""),
                file_pattern=(str(args.get("file_pattern")) if args.get("file_pattern") else None),
                limit=_int(args.get("limit"), default=100),
            )
        if tool_name == "roo_write_file_preview":
            return roo_tools.write_file_preview(
                path=str(args.get("path") or ""),
                content=str(args.get("content") or ""),
            )
        if tool_name == "roo_write_file":
            return roo_tools.write_file(
                path=str(args.get("path") or ""),
                content=str(args.get("content") or ""),
                approval=str(args.get("approval") or ""),
            )
        if tool_name == "roo_apply_patch_preview":
            return roo_tools.apply_patch_preview(patch=str(args.get("patch") or ""))
        if tool_name == "roo_apply_patch":
            return roo_tools.apply_patch(
                patch=str(args.get("patch") or ""),
                approval=str(args.get("approval") or ""),
            )
        if tool_name == "roo_execute_command":
            return roo_tools.execute_command(
                command=str(args.get("command") or ""),
                approval=str(args.get("approval") or ""),
                timeout=_int(args.get("timeout"), default=20),
            )
        if tool_name == "roo_attempt_completion":
            return roo_tools.attempt_completion(
                result=str(args.get("result") or ""),
                command=(str(args.get("command")) if args.get("command") else None),
            )
        if tool_name == "roo_ask_followup_question":
            return roo_tools.ask_followup_question(
                question=str(args.get("question") or ""),
            )
        return _tool_result(
            tool_name,
            "error",
            stderr=f"Unknown Roo adapter tool: {tool_name}",
            source="roo_tools.local_adapter",
        )

    def _roo_status(self) -> dict[str, Any]:
        try:
            from controller.roo_tools import roo_tools_status

            return roo_tools_status()
        except Exception as exc:
            return {
                "status": "unavailable",
                "available": False,
                "reason": str(exc),
                "fake_success": False,
            }

    def _request(self) -> Any:
        if self.app is None:
            state = SimpleNamespace(training_storage=self.storage, training_events=[])
            return SimpleNamespace(app=SimpleNamespace(state=state))
        if not hasattr(self.app.state, "training_storage"):
            self.app.state.training_storage = self.storage
        if not hasattr(self.app.state, "training_events"):
            self.app.state.training_events = []
        return SimpleNamespace(app=self.app)

    def _store_learning_action(
        self,
        tool_name: str,
        document: str,
        approval_status: str,
        source: str,
        source_type: str,
        metadata_11d: dict[str, Any] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any], str | None, str]:
        document = str(document or "").strip()
        if not document:
            return False, metadata_11d or {}, None, "Nothing to store."

        base_metadata = metadata_11d or _action_metadata(tool_name, document, approval_status, source, source_type)
        embedding = _embedding_11d(tool_name, document)
        geometry = _geometry_11d(embedding)
        result_metadata = {**base_metadata, "geometry_11d": geometry}
        storage_metadata = _flatten_metadata(
            {
                **base_metadata,
                **(extra_metadata or {}),
                "type": "agent_learning_action_11d",
                "tool_name": tool_name,
                "approval_status": approval_status,
                "source": source,
                "source_type": source_type,
                "content_hash": hashlib.sha256(document.encode("utf-8", errors="replace")).hexdigest(),
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "geometry_11d_available": bool(geometry.get("available")),
                "geometry_11d_source": geometry.get("source", "unavailable"),
            }
        )
        if geometry.get("available"):
            if "volume" in geometry:
                storage_metadata["geometry_11d_volume"] = geometry["volume"]
            if "oppervlakte" in geometry:
                storage_metadata["geometry_11d_oppervlakte"] = geometry["oppervlakte"]

        try:
            collection = _training_collection()
            item_id = f"agent_learning_{tool_name}_{uuid.uuid4()}"
            collection.add(
                ids=[item_id],
                documents=[document[:6000]],
                metadatas=[storage_metadata],
                embeddings=[embedding],
            )
            return True, result_metadata, item_id, "Stored in local 11D ChromaDB training collection."
        except Exception as exc:
            return False, result_metadata, None, f"11D ChromaDB unavailable; learning was not faked: {exc}"

    def _autonomy_for(self, result: dict[str, Any]) -> dict[str, Any]:
        tool = result.get("tool_name")
        if tool in {"memory_search", "agentic_ecosystem_context", "prompt_understanding", "self_training_plan", "inspect_hippocampus"}:
            return {"level": "high", "label": "High: local memory and planning first", "memory_first": True}
        if tool in {"scrub_browser_content", "training_ingest", "safe_shell", "run_tests", "mail_send_preview", "social_post_preview", "voice_chat_status"}:
            return {"level": "medium", "label": "Medium: approval-gated local action", "memory_first": True}
        if str(tool or "").startswith("roo_"):
            return {"level": "medium", "label": "Medium: Roo adapter under workspace/approval gates", "memory_first": True}
        if tool in {"browser_research", "chatgpt_browser_ask", "brave_search", "ns_travel_advice", "world_grok_ask", "mail_read_recent", "mail_send", "social_post_publish", "codex_job_start", "resolve_or_build_function"}:
            return {"level": "guarded", "label": "Guarded: external/browser perimeter", "memory_first": True}
        return {"level": "unknown", "label": "No registered tool result yet", "memory_first": False}


def _brave_companion_for_browser_research(query: str, approval: str, limit: int = 5) -> dict[str, Any]:
    if not approval_matches(approval):
        return {
            "status": "blocked",
            "provider": "brave",
            "approval_required": True,
            "reason": "Brave companion search waits for Philip Akkoord.",
            "fake_success": False,
        }
    try:
        from controller.brave_search import search_brave_llm_context

        result = search_brave_llm_context(query, maximum_number_of_urls=max(1, min(int(limit or 5), 20)))
        result.setdefault("provider", "brave")
        result.setdefault("route", "brave_companion_search")
        result.setdefault("fake_success", False)
        return result
    except Exception as exc:
        return {"status": "error", "provider": "brave", "reason": str(exc), "fake_success": False}


def _agentic_ecosystem_stdout(payload: dict[str, Any]) -> str:
    sources = ", ".join(payload.get("sources") or []) or "geen bronnen"
    lines = [
        f"Agentic ecosystem context: {sources}",
        str(payload.get("visible_summary") or "").strip(),
    ]
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), list) else []
    roles = payload.get("roles") if isinstance(payload.get("roles"), list) else []
    if roles:
        lines.append("Rollen: " + ", ".join(str(item.get("label") or item.get("id") or "role") for item in roles[:8] if isinstance(item, dict)))
    if patterns:
        lines.append("Patronen: " + ", ".join(str(item.get("label") or item.get("id") or "pattern") for item in patterns[:6] if isinstance(item, dict)))
    recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
    for item in recommendations[:4]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('label')}: {item.get('action')}")
    return "\n".join(line for line in lines if line).strip()


def understand_prompt(prompt: str) -> dict[str, Any]:
    text = str(prompt or "").strip()
    lowered = text.lower()
    urls = URL_RE.findall(text)
    keywords = _keywords(text)
    asks_current = any(
        marker in lowered
        for marker in (
            "laatste",
            "nieuws",
            "vandaag",
            "internet",
            "browser",
            "zoek op",
            "onderzoek",
            "latest",
            "current",
            "recent",
        )
    )
    wants_training = any(marker in lowered for marker in ("train", "leer", "onthoud", "ingest", "sla op"))
    wants_shell = any(marker in lowered for marker in ("run tests", "pytest", "unittest", "shell", "commando"))
    wants_chatgpt = "chatgpt" in lowered
    wants_agentic_ecosystem = _wants_agentic_ecosystem(lowered)
    approval_detected = approval_matches(text)

    missing_knowledge: list[dict[str, Any]] = []
    if asks_current:
        missing_knowledge.append(
            {
                "kind": "external_or_current_information",
                "reason": "Prompt asks for recent/browser/internet knowledge that local memory may not contain.",
                "query": _research_query(text, keywords),
                "tool": "browser_research",
                "approval_required": True,
            }
        )
    if wants_training:
        missing_knowledge.append(
            {
                "kind": "durable_training_target",
                "reason": "Prompt asks to learn or ingest knowledge.",
                "tool": "training_ingest",
                "approval_required": True,
            }
        )
    if wants_agentic_ecosystem:
        missing_knowledge.append(
            {
                "kind": "local_agentic_ecosystem",
                "reason": "Prompt asks about agentic work, agents, DeepSeek or Atlas patterns.",
                "tool": "agentic_ecosystem_context",
                "approval_required": False,
            }
        )

    candidate_actions: list[dict[str, Any]] = []
    if wants_shell:
        candidate_actions.append({"tool": "run_tests", "approval_required": True})
    if wants_chatgpt:
        candidate_actions.append({"tool": "chatgpt_browser_ask", "approval_required": True})
    if wants_training:
        candidate_actions.append({"tool": "training_ingest", "approval_required": True})
    if asks_current:
        candidate_actions.append({"tool": "browser_research", "approval_required": True})
    if wants_agentic_ecosystem:
        candidate_actions.append({"tool": "agentic_ecosystem_context", "approval_required": False})

    return {
        "philip_opdracht": text,
        "language_hint": "nl" if _looks_dutch(lowered) else "unknown",
        "keywords": keywords,
        "urls": urls,
        "needs_memory_search": True,
        "needs_browser_research": asks_current,
        "missing_knowledge": missing_knowledge,
        "candidate_actions": candidate_actions,
        "approval_detected": approval_detected,
        "approval_phrase": "Akkoord",
        "research_query": _research_query(text, keywords),
        "next_action": "Run memory_search first, then request approved browser_research if knowledge is still missing.",
    }


def _wants_agentic_ecosystem(lowered: str) -> bool:
    if any(marker in lowered for marker in ("deepseek", "atlas", "agentisch", "agentic", "sub-agent", "subagent", "multi-agent", "sdd")):
        return True
    if any(marker in lowered for marker in ("workflow", "orchestratie", "delegatie", "delegate", "handoff")):
        return any(marker in lowered for marker in ("agent", "agents", "tool", "tools", "werk", "werken", "work"))
    if "agents" in lowered:
        return any(marker in lowered for marker in ("werken met", "werk met", "agent runtime", "slash", "catalogus", "capabilities"))
    return False


def _preview_payload_local(
    url: str,
    browser_text: str,
    title: str,
    target_hz: float | None,
    approval: str | None,
    request: Any,
) -> dict[str, Any]:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() == TEACHABLE_MACHINE_HOST:
        scrubbed = prepare_teachablemachine_ingest(
            url=url,
            browser_text=browser_text,
            approval=approval,
            title=title,
        )
    else:
        scrubbed = prepare_browser_ingest(
            url=url,
            browser_text=browser_text,
            approval=approval,
            title=title,
        )

    raw_item = scrubbed.to_raw_item(title=title)
    item = normalize(raw_item)
    resonance = stream_resonance_score(item, persona="philip")
    importance = _resonance_to_importance(resonance.score)
    dream = DreamCycle.from_env().sample(f"{item.published_at}|{item.content_hash}|{item.source_hash}")
    dream_hz = max(418.0, min(432.0, float(target_hz))) if target_hz is not None else float(dream.hz)
    frequency_source = "manual_ui" if target_hz is not None else "dreamcycle"
    metadata_11d = build_11d_metadata(
        item=item,
        resonance_score=resonance.score,
        importance=importance,
        ingested_at=scrubbed.scrubbed_at,
        dream_hz=dream_hz,
        relative_temporal_position=dream.relative_temporal_position,
    )
    return {
        "status": "preview",
        "source_url": scrubbed.source_url,
        "source_host": scrubbed.source_host,
        "taint": scrubbed.taint,
        "approval_status": scrubbed.approval_status,
        "requires_approval": scrubbed.requires_approval,
        "approval_phrase": scrubbed.approval_phrase,
        "blocked_patterns": list(scrubbed.blocked_patterns),
        "allowed_actions": list(scrubbed.allowed_actions),
        "blocked_actions": list(scrubbed.blocked_actions),
        "diff_hash": scrubbed.diff_hash,
        "diff_view": scrubbed.diff_view,
        "scrubbed_text": scrubbed.scrubbed_text,
        "raw_item": raw_item,
        "resonance": {
            "score": resonance.score,
            "should_store": resonance.should_store,
            "should_propose": resonance.should_propose,
            "reasons": resonance.reasons,
            "matched_domains": resonance.matched_domains,
        },
        "dreamcycle": {
            **dream.metadata(),
            "dream_hz": round(dream_hz, 6),
            "frequency_source": frequency_source,
            "samples": _frequency_samples(item.content_hash, target_hz=dream_hz),
        },
        "metadata_11d": metadata_11d,
        "missing_11d_layers": missing_11d_layers(metadata_11d),
        "collection_count": _safe_total_count(getattr(getattr(request, "app", None), "state", None)),
        "pipeline": [
            {"step": "observe", "label": "Browser snapshot", "value": f"{len(browser_text)} chars"},
            {
                "step": "orient",
                "label": "Scrubber",
                "value": "clean" if not scrubbed.blocked_patterns else ",".join(scrubbed.blocked_patterns),
            },
            {"step": "decide", "label": "Resonance", "value": f"{resonance.score:.3f}"},
            {"step": "act", "label": "Approval gate", "value": scrubbed.approval_status},
            {"step": "reflect", "label": "DreamCycle", "value": f"{dream_hz:.3f} Hz"},
        ],
    }


def _remember_event_local(request: Any, kind: str, payload: dict[str, Any]) -> None:
    try:
        state = request.app.state
        events = list(getattr(state, "training_events", []))
        events.append(
            {
                "kind": kind,
                "source_host": payload.get("source_host"),
                "approval_status": payload.get("approval_status"),
                "stored": payload.get("stored", False),
                "dream_hz": payload.get("dreamcycle", {}).get("dream_hz"),
                "resonance_score": payload.get("resonance", {}).get("score"),
                "collection_count": payload.get("collection_count"),
            }
        )
        state.training_events = events[-20:]
    except Exception:
        return


def _safe_total_count(storage_or_state: Any) -> int:
    storage = getattr(storage_or_state, "training_storage", storage_or_state)
    return _safe_collection_count(storage) + _safe_training_collection_count()


def _safe_collection_count(storage: Any) -> int:
    try:
        collection = getattr(storage, "_collection", None)
        if collection is None and hasattr(storage, "collection"):
            collection = storage.collection
        return int(collection.count()) if collection is not None else 0
    except Exception:
        return 0


def _safe_training_collection_count() -> int:
    try:
        return int(_training_collection().count())
    except Exception:
        return 0


def _training_collection():
    try:
        from controller.chroma_runtime import get_or_create_collection
    except Exception as exc:
        raise RuntimeError(f"chroma runtime is not available: {exc}") from exc
    collection_name = os.getenv("WINTRIP_TRAINING_COLLECTION", "wintrip_training_11d")
    return get_or_create_collection(name=collection_name, persist_dir=os.getenv("WINTRIP_DB_PATH", "wintrip_brain"))


def _frequency_samples(seed: str, target_hz: float | None = None) -> list[dict[str, float]]:
    cycle = DreamCycle.from_env()
    samples: list[dict[str, float]] = []
    for index in range(12):
        sample = cycle.sample(seed, stable_seconds=index * (cycle.cycle_seconds / 12.0))
        hz = float(sample.hz)
        if target_hz is not None:
            pulse = 0.25 + (0.5 if index in {3, 7, 11} else 0.0)
            hz = max(418.0, min(432.0, hz * (1.0 - pulse) + float(target_hz) * pulse))
        samples.append({"index": index, "hz": round(hz, 3), "phase": round(sample.phase, 4)})
    return samples


def _tool_result(
    tool_name: str,
    status: str,
    result: Any = None,
    stdout: str = "",
    stderr: str = "",
    source: str = "agent_tools",
    approval_status: str = "not_required",
    stored_to_memory: bool = False,
    metadata_11d: dict[str, Any] | None = None,
    next_action: str = "done",
) -> dict[str, Any]:
    stderr = stderr or ""
    return {
        "status": status,
        "tool_name": tool_name,
        "stdout": stdout or "",
        "stderr": stderr,
        "result": result if result is not None else {},
        "source": source,
        "approval_status": approval_status,
        "stored_to_memory": bool(stored_to_memory),
        "metadata_11d": metadata_11d or {},
        "next_action": next_action,
        "error": stderr,
    }


def _ns_api_key() -> str:
    for name in ("WINTRIP_NS_API_KEY", "NS_API_KEY", "NS_APP_API_KEY", "NS_API_SUBSCRIPTION_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _ns_datetime(*, date: str = "", time_value: str = "", datetime_value: str = "") -> str:
    if datetime_value.strip():
        return datetime_value.strip()
    time_value = str(time_value or "").strip().replace(".", ":")
    date = str(date or "").strip()
    if not date and not time_value:
        return ""
    if not date:
        date = datetime.now().astimezone().date().isoformat()
    if not time_value:
        time_value = datetime.now().astimezone().strftime("%H:%M")
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_value)
    if match:
        time_value = f"{int(match.group(1)):02d}:{match.group(2)}"
    return f"{date}T{time_value}:00"


def _ns_planner_url(from_station: str, to_station: str, *, date_time: str = "", search_for_arrival: bool = False) -> str:
    params = {
        "vertrek": from_station,
        "vertrektype": "treinstation",
        "aankomst": to_station,
        "aankomsttype": "treinstation",
        "type": "aankomst" if search_for_arrival else "vertrek",
    }
    if date_time:
        params["tijd"] = date_time[:16]
    return "https://www.ns.nl/reisplanner/#/?" + urlencode(params)


def _summarize_ns_trips(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    trips = raw.get("trips")
    if not isinstance(trips, list):
        return []
    output: list[dict[str, Any]] = []
    for trip in trips[:4]:
        if not isinstance(trip, dict):
            continue
        legs = [leg for leg in (trip.get("legs") or []) if isinstance(leg, dict)]
        first_leg = legs[0] if legs else {}
        last_leg = legs[-1] if legs else {}
        summary = {
            "status": trip.get("status"),
            "transfers": trip.get("transfers"),
            "planned_duration_minutes": trip.get("plannedDurationInMinutes") or trip.get("durationInMinutes"),
            "actual_duration_minutes": trip.get("actualDurationInMinutes"),
            "departure_time": _ns_time(
                trip.get("actualDepartureTime")
                or trip.get("plannedDepartureTime")
                or _ns_nested(first_leg, "origin", "actualDateTime")
                or _ns_nested(first_leg, "origin", "plannedDateTime")
                or first_leg.get("actualDepartureTime")
                or first_leg.get("plannedDepartureTime")
            ),
            "arrival_time": _ns_time(
                trip.get("actualArrivalTime")
                or trip.get("plannedArrivalTime")
                or _ns_nested(last_leg, "destination", "actualDateTime")
                or _ns_nested(last_leg, "destination", "plannedDateTime")
                or last_leg.get("actualArrivalTime")
                or last_leg.get("plannedArrivalTime")
            ),
            "legs": [_summarize_ns_leg(leg) for leg in legs[:6]],
            "messages": [
                _ns_message_text(message)[:280]
                for message in (trip.get("messages") or [])
                if isinstance(message, (dict, str))
            ],
        }
        output.append(summary)
    return output


def _summarize_ns_leg(leg: dict[str, Any]) -> dict[str, Any]:
    product = leg.get("product") if isinstance(leg.get("product"), dict) else {}
    return {
        "name": leg.get("name") or product.get("longCategoryName") or product.get("categoryCode"),
        "direction": leg.get("direction"),
        "origin": _ns_nested(leg, "origin", "name"),
        "destination": _ns_nested(leg, "destination", "name"),
        "departure_time": _ns_time(_ns_nested(leg, "origin", "actualDateTime") or _ns_nested(leg, "origin", "plannedDateTime")),
        "arrival_time": _ns_time(_ns_nested(leg, "destination", "actualDateTime") or _ns_nested(leg, "destination", "plannedDateTime")),
        "departure_track": _ns_nested(leg, "origin", "actualTrack") or _ns_nested(leg, "origin", "plannedTrack"),
        "arrival_track": _ns_nested(leg, "destination", "actualTrack") or _ns_nested(leg, "destination", "plannedTrack"),
    }


def _ns_nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _ns_message_text(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("text") or message.get("message") or message.get("title") or "")
    return str(message or "")


def _ns_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"T(\d{2}:\d{2})", text)
    return match.group(1) if match else text[:16]


def _compact_mail_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"status": "Unknown", "body_excerpt": _redact_operational_text(str(item))[:900]}
    compact: dict[str, Any] = {}
    preferred = ("status", "from", "sender", "to", "subject", "date", "error", "body", "text", "summary")
    for key in preferred:
        if key not in item:
            continue
        value = item.get(key)
        out_key = "body_excerpt" if key in {"body", "text"} else key
        if isinstance(value, str):
            compact[out_key] = _redact_operational_text(value)[:1200 if out_key == "body_excerpt" else 500]
        else:
            compact[out_key] = value
    for key, value in item.items():
        if key in compact or key in preferred:
            continue
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("password", "token", "secret", "key", "bearer", "authorization")):
            compact[str(key)] = "[REDACTED]"
        elif isinstance(value, str):
            compact[str(key)] = _redact_operational_text(value)[:400]
        elif isinstance(value, (int, float, bool)) or value is None:
            compact[str(key)] = value
        if len(compact) >= 12:
            break
    return compact


def _redact_operational_text(text: str) -> str:
    redacted = str(text or "")
    patterns = (
        re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s,;}]+"),
        re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
    )
    for pattern in patterns:
        redacted = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]" if match.groups() else "[REDACTED]", redacted)
    return redacted


def _coherence_metadata(tool_name: str, payload: str) -> dict[str, Any]:
    """Coherence wrapper voor tool-bridge acties."""

    try:
        from ouroboros_esoteric.entropy_monitor import EntropyMonitor
        from ouroboros_esoteric.light_language import LightLanguageCompiler

        entropy = EntropyMonitor().measure({"tool": tool_name, "payload": payload})
        firewall = LightLanguageCompiler().coherence_check(
            payload,
            input_frequency=528.0,
            entropy_level=float(entropy.get("entropy_level") or 0.0),
        )
        return {
            "coherence_firewall": {
                "tool": tool_name,
                "status": firewall.get("status"),
                "resonant": firewall.get("resonant"),
                "healed": firewall.get("healed"),
                "entropy": entropy,
            }
        }
    except Exception as exc:
        return {"coherence_firewall": {"tool": tool_name, "status": "unavailable", "reason": str(exc)}}


def _rank_training_records(query: str, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        records = _training_collection().get(limit=80, include=["documents", "metadatas"])
    except Exception as exc:
        return [], [f"wintrip_training_11d: {exc}"]
    terms = {term.lower() for term in WORD_RE.findall(query)}
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item_id, doc, meta in zip(records.get("ids", []), records.get("documents", []), records.get("metadatas", [])):
        haystack = f"{doc} {json.dumps(meta, ensure_ascii=False)}".lower()
        score = sum(1 for term in terms if term in haystack)
        ranked.append(
            (
                score,
                {
                    "id": item_id,
                    "source": "wintrip_training_11d",
                    "text": str(doc)[:900],
                    "metadata": meta,
                    "score": score,
                },
            )
        )
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for score, item in ranked[:limit] if score > 0 or not terms][:limit], []


def _action_metadata(tool_name: str, document: str, approval_status: str, source: str, source_type: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    frequency = _frequency_for(tool_name, document)
    digest = hashlib.sha256(document.encode("utf-8", errors="replace")).hexdigest()
    return {
        "dimension_count": 11,
        "d1_physical_body": "agent_learning_action",
        "d2_physical_source": source_type,
        "d3_physical_container": "hippocampus_chromadb",
        "d4_chronology": now,
        "d5_persona_actor": "philip",
        "d6_persona_intent": "observe_orient_decide_act_reflect",
        "d7_persona_relation": "wintrip_self_training_loop",
        "d8_karmic_taint": f"local_tool:{approval_status}",
        "d9_resonance_frequency": f"{frequency:.6f}Hz",
        "d10_resonance_score": "0.650000:importance=3.0",
        "d11_field": f"ouroboros_field:tool={tool_name}:hash={digest[:12]}",
        "tool_name": tool_name,
        "approval_status": approval_status,
        "dream_hz": frequency,
        "source": source,
        "source_type": source_type,
    }


def _embedding_11d(tool_name: str, document: str) -> list[float]:
    digest = hashlib.sha256(f"{tool_name}|{document}".encode("utf-8", errors="replace")).digest()
    values: list[float] = []
    for index in range(11):
        start = (index * 2) % len(digest)
        chunk = digest[start:start + 2]
        if len(chunk) < 2:
            chunk += digest[: 2 - len(chunk)]
        raw = int.from_bytes(chunk, "big")
        values.append(round((raw / 65535.0) * 2.0 - 1.0, 6))
    return values


def _geometry_11d(embedding: list[float]) -> dict[str, Any]:
    for module_name in ("controller.stream.geometry_11d", "geometry_11d"):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            last_error = str(exc)
            continue
        for fn_name in ("compute_geometry_11d", "measure_geometry_11d", "geometry_11d"):
            fn = getattr(module, fn_name, None)
            if not callable(fn):
                continue
            try:
                raw = fn(embedding)
            except Exception as exc:
                return {"available": False, "source": module_name, "reason": str(exc)}
            normalized = _normalize_geometry(raw)
            normalized["available"] = True
            normalized["source"] = f"{module_name}.{fn_name}"
            return normalized
        return {"available": False, "source": module_name, "reason": "No supported geometry function found."}
    return {
        "available": False,
        "source": "unavailable",
        "reason": f"geometry_11d module not available: {locals().get('last_error', 'not found')}",
    }


def _normalize_geometry(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        volume = raw.get("volume") or raw.get("volume_11d")
        oppervlakte = raw.get("oppervlakte") or raw.get("surface_area") or raw.get("surface")
    else:
        volume = getattr(raw, "volume", None)
        oppervlakte = getattr(raw, "oppervlakte", None) or getattr(raw, "surface_area", None)
    normalized: dict[str, Any] = {}
    if _is_number(volume):
        normalized["volume"] = float(volume)
    if _is_number(oppervlakte):
        normalized["oppervlakte"] = float(oppervlakte)
    return normalized


def _flatten_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    flat: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            flat[key] = value
        else:
            flat[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)[:1000]
    return flat


def _frequency_for(tool_name: str, document: str) -> float:
    raw = int(hashlib.sha256(f"{tool_name}|{document}".encode("utf-8", errors="replace")).hexdigest()[:8], 16)
    return round(418.0 + (raw / 0xFFFFFFFF) * 14.0, 6)


def _keywords(text: str) -> list[str]:
    stop = {
        "het",
        "een",
        "met",
        "voor",
        "over",
        "the",
        "and",
        "that",
        "this",
        "philip",
        "akkoord",
    }
    words = []
    for word in WORD_RE.findall(text.lower()):
        if word not in stop and word not in words:
            words.append(word)
        if len(words) >= 12:
            break
    return words


def _research_query(text: str, keywords: list[str]) -> str:
    urls = URL_RE.findall(text)
    if urls:
        return urls[0]
    if keywords:
        return " ".join(keywords[:8])
    return text[:120]


def _looks_dutch(lowered: str) -> bool:
    return any(marker in lowered for marker in (" de ", " het ", " een ", " leer ", "zoek", "onderzoek", "opdracht"))


def _looks_like_failure(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("fout", "error", "traceback", "crash", "failed"))


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
