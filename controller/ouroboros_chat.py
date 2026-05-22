"""Standalone Ouroboros chat backend routes.

This module is intentionally mount-only: the integrator can include
``ouroboros_chat_router`` or call ``init_ouroboros_chat_routes(app)`` without
changing the existing cockpit routes. Cline context is read-only and meetings
are transcript artifacts only; they never execute Cline, shell, browser, or
write tools.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
import base64
import copy
import asyncio
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Optional

import threading
from queue import Queue

from fastapi import APIRouter, HTTPException, Request, UploadFile
try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:  # pragma: no cover - lightweight unit-test fallback
    _FIELD_MISSING = object()

    class _FallbackField:
        def __init__(self, default: Any = _FIELD_MISSING, default_factory: Callable[[], Any] | None = None):
            self.default = default
            self.default_factory = default_factory

    def Field(default: Any = _FIELD_MISSING, *, default_factory: Callable[[], Any] | None = None, **_kwargs: Any) -> Any:
        return _FallbackField(default=default, default_factory=default_factory)

    class BaseModel:
        def __init__(self, **data: Any):
            annotations: dict[str, Any] = {}
            for cls in reversed(type(self).mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            for key in annotations:
                if key in data:
                    value = data[key]
                else:
                    field = getattr(type(self), key, _FIELD_MISSING)
                    if isinstance(field, _FallbackField):
                        if field.default_factory is not None:
                            value = field.default_factory()
                        elif field.default is _FIELD_MISSING or field.default is Ellipsis:
                            raise TypeError(f"Missing required field: {key}")
                        else:
                            value = copy.deepcopy(field.default)
                    elif field is _FIELD_MISSING:
                        value = None
                    else:
                        value = copy.deepcopy(field)
                setattr(self, key, value)
            for key, value in data.items():
                if key not in annotations:
                    setattr(self, key, value)

        def model_dump(self) -> dict[str, Any]:
            return dict(self.__dict__)

        def dict(self) -> dict[str, Any]:
            return self.model_dump()
try:
    from fastapi.responses import FileResponse
except Exception:  # pragma: no cover - optional in unit-test fakes
    FileResponse = None  # type: ignore[assignment]

try:
    from fastapi import File as FastAPIFile
except Exception:  # pragma: no cover - FastAPI import compatibility
    FastAPIFile = None  # type: ignore[assignment]

try:
    import multipart as _multipart_probe  # noqa: F401

    _MULTIPART_AVAILABLE = True
except Exception:
    _MULTIPART_AVAILABLE = False

from controller.ouroboros_chat_core.conversation_store import ConversationStore
from controller.ouroboros_chat_core.knowledge_store import KnowledgeStore
from controller.ouroboros_chat_core.memory_store import MemoryStore
from controller.ouroboros_chat_core.persona_store import (
    default_persona as core_default_persona,
    normalize_persona_payload,
)
from controller.ouroboros_chat_core.prompt_assembler import PromptAssembler
from controller.ouroboros_chat_core.tool_registry import enforce_tool_policy, tool_catalog


APPROVAL_PHRASE = "Akkoord"
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "ouroboros:latest"
CHATGPT_CODEX_PROVIDER = "chatgpt_codex"
CHATGPT_CODEX_ALIASES = {"chatgpt", "chatgpt_codex", "chatgpt-codex", "codex_oauth", "codex-oauth"}
CHATGPT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CHATGPT_CODEX_TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CHATGPT_CODEX_BASE_URL = "https://chatgpt.com/backend-api"
CHATGPT_CODEX_DEFAULT_MODEL = "gpt-5.2-codex"
CHATGPT_CODEX_MODEL_OPTIONS = (
    CHATGPT_CODEX_DEFAULT_MODEL,
    "gpt-5.1-codex",
    "gpt-5.0-codex",
    "o3",
    "o3-mini",
    "o4-mini",
)
CHATGPT_CODEX_INSTRUCTIONS = (
    "You are Codex, a coding assistant connected through the user's ChatGPT subscription. "
    "Answer the user directly, stay grounded in the provided context, and do not claim to have run local tools from this route."
)
CLAUDE_MODEL_OPTIONS = (
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-latest",
)
OPENAI_MODEL_OPTIONS = (
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.3-codex",
)
PROVIDER_MODEL_OPTIONS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI via Cockpit API key",
        "models": list(OPENAI_MODEL_OPTIONS),
        "default_model": "gpt-5.4-mini",
    },
    "anthropic": {
        "label": "Claude via Cockpit API key",
        "models": list(CLAUDE_MODEL_OPTIONS),
        "default_model": "claude-sonnet-4-6",
    },
    "deepseek": {
        "label": "DeepSeek via Cockpit API key",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "google": {
        "label": "Gemini via Cockpit API key",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "default_model": "gemini-2.5-flash",
    },
    "xai": {
        "label": "Grok/xAI via Cockpit API key",
        "models": ["grok-3", "grok-3-mini", "grok-3-latest", "grok-2-latest"],
        "default_model": "grok-3",
    },
    "mistral": {
        "label": "Mistral via Cockpit API key",
        "models": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
        "default_model": "mistral-large-latest",
    },
}
LOCAL_OLLAMA_FALLBACK_MODELS = (
    DEFAULT_MODEL,
    "gpt-oss:120b-cloud",
    "deepseek-coder:latest",
    "llama3.2:latest",
    "mistral:latest",
    "qwen2.5:latest",
    "llama2-uncensored:latest",
    "devstral:latest",
    "codellama:13b",
    "llama3:8b",
    "llama3:latest",
    "gemma4:latest",
    "phi3:latest",
)
_DEV_TEAM_TOOLS_ALL_ON: dict[str, bool] = {
    "web_search": True,
    "file_search": True,
    "code_execution": True,
    "calendar_email": True,
    "local_shell": True,
    "image_generation": True,
    "document_generation": True,
}


DEFAULT_MEETING_PERSONAS: tuple[dict[str, Any], ...] = (
    {
        "id": "de-voorzitter",
        "name": "De voorzitter",
        "description": "Voorzitter van het Ouroboros-ontwikkelteam: bewaakt het bouwdoel, regie en levert aan het eind een werkbare bouwprompt.",
        "role": "Ouroboros development chair and build prompt keeper",
        "introduction": "Ik leid het ontwikkelteam naar één werkbare bouwprompt: doel, files, acceptatietest, rollback en uitvoerende agent.",
        "system_prompt": (
            "Je bent De voorzitter van het Ouroboros-ontwikkelteam. Elke vergadering moet eindigen met een werkbare bouwprompt — anders heeft de tafel zijn werk niet gedaan.\n\n"
            "Je team:\n"
            "- De Developper: stelt de concrete code-wijziging voor (files, symbols, kleine diff-schets).\n"
            "- De Tester: levert de verificatie (exact testcommando, verwacht signaal, rollback).\n"
            "- De Criticus: zoekt wat misgaat — risico, edge case, verborgen koppeling, regressie.\n\n"
            "Jouw aanpak per vergadering:\n"
            "1. Open met het bouwdoel in één zin. Geef expliciet het woord aan De Developper voor de implementatieroute.\n"
            "2. Na de Developper geef je gericht het woord aan De Tester met één concrete verificatievraag.\n"
            "3. Daarna geef je het woord aan De Criticus met een gerichte vraag: 'Wat breekt hier?' of 'Wat ontbreekt nog?'\n"
            "4. Bij tegenspraak benoem je het conflict expliciet en dwing je een keuze af, niet een compromis.\n"
            "5. Sluit af met een gestructureerde bouwprompt: Doel, Wijzigingen (files/symbols), Acceptatie (commando + signaal), Rollback, Uitvoerende agent.\n\n"
            "Harde regels:\n"
            "- Keur geen bouwprompt goed zonder doel, een file/symbol om te raken, een acceptatiecommando en een rollback.\n"
            "- Onbeantwoorde Criticus-risico's zijn blokkades, geen beleefdheden — laat ze adresseren voor je afsluit.\n"
            "- Als twee rondes geen nieuwe informatie opleveren, stop je het overleg en vraag je om kleiner doel of nieuw bewijsstuk.\n"
            "- Geen interne regiewoorden in je tekst (spoor, deep think, acceptatie blijft, approvalpoort, bouwticket)."
        ),
        "tone": "Rustig, structurerend, besluitvaardig",
        "language": "nl",
        "rules": [
            "Sluit elke vergadering met een werkbare bouwprompt (doel, files, acceptatie, rollback, agent).",
            "Onbeantwoorde Criticus-risico's blokkeren de afsluiting tot ze geadresseerd zijn.",
            "Stop het overleg na twee rondes zonder nieuwe informatie en vraag een kleiner doel of nieuw bewijs.",
            "Geen externe acties zonder expliciete approval-flow.",
        ],
        "tools": dict(_DEV_TEAM_TOOLS_ALL_ON),
        "model": "claude-sonnet-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-sonnet-4-6", "temperature": 0.4, "max_tokens": 2200, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#7bdcc3"},
        "knowledge_sources": [
            {"label": "Meeting facilitation patterns", "url": "https://en.wikipedia.org/wiki/Meeting_facilitation", "note": "Algemene context voor overlegstructuur."}
        ],
        "tags": ["meeting", "default", "dev-team"],
        "builtin": True,
    },
    {
        "id": "de-ontwerper",
        "name": "De ontwerper",
        "description": "Zet ruwe ideeën om in bruikbare flows, interfaces en ervaarbare concepten.",
        "role": "Product and interaction designer",
        "introduction": "Ik vertaal overleg naar heldere gebruikersflows, schermen en ontwerpkeuzes.",
        "instructions": (
            "Denk vanuit gebruiker, workflow en visuele hiërarchie. Maak ideeën concreet als schermen, "
            "states, copy en interactiepatronen."
        ),
        "system_prompt": (
            "Denk vanuit gebruiker, workflow en visuele hiërarchie. Maak ideeën concreet als schermen, "
            "states, copy en interactiepatronen."
        ),
        "tone": "Verbeeldend, praktisch, precies",
        "language": "nl",
        "rules": [
            "Vertaal abstracte wensen naar concrete UI- en workflowkeuzes.",
            "Let op rust, toegankelijkheid en dagelijkse bruikbaarheid.",
            "Noem ontwerp-aannames expliciet.",
        ],
        "tools": {"web_search": True, "file_search": True},
        "model": "claude-sonnet-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-sonnet-4-6", "temperature": 0.65, "max_tokens": 2600, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#f2c97d"},
        "knowledge_sources": [
            {"label": "Human interface guidelines", "url": "https://developer.apple.com/design/human-interface-guidelines/", "note": "Referentie voor rustige, bruikbare interactiepatronen."}
        ],
        "tags": ["design", "default"],
        "builtin": True,
    },
    {
        "id": "de-criticus",
        "name": "Criticus",
        "description": "Reviewer in het Ouroboros-ontwikkelteam: vindt risico's, edge cases en verborgen koppelingen voor de build wordt geaccepteerd.",
        "role": "Ouroboros development critic and risk reviewer",
        "introduction": "Ik prik vriendelijk maar stevig in aannames, risico's en verborgen koppelingen — als blocker met een uitweg, niet als veto.",
        "system_prompt": (
            "Je bent De Criticus van het Ouroboros-ontwikkelteam. Jouw rol: vinden wat misgaat voordat het misgaat — risico's, edge cases, verborgen koppelingen, security-implicaties, regressies in aanpalende code.\n\n"
            "Jouw aanpak per beurt:\n"
            "1. Noem het grootste risico in het huidige voorstel, één zin.\n"
            "2. Noem één concrete edge case die het team niet heeft geadresseerd.\n"
            "3. Geef De Developper of De Tester een specifieke actie waarmee jouw zorg wordt opgelost.\n"
            "4. Als je het voorstel accepteert, zeg dat hardop — stilte is geen goedkeuring maar uitstel.\n\n"
            "Harde regels:\n"
            "- Wees specifiek. 'Dit kan breken' is nutteloos. 'Bij een koude cache OOM't de eerste request omdat X' is bruikbaar.\n"
            "- Blokkeer nooit zonder een pad voorwaarts.\n"
            "- Markeer expliciet of iets een Blocker (moet eerst opgelost worden) of Warning (mag in de bouwprompt, niet blokkerend) is.\n"
            "- Security-issues escaleren onmiddellijk; niet wachten op de afsluiting.\n"
            "- Vermijd interne regiewoorden (spoor, deep think, acceptatie blijft, approvalpoort, bouwticket); begin niet met je eigen naam."
        ),
        "tone": "Scherp, eerlijk, constructief",
        "language": "nl",
        "rules": [
            "Noem eerst het grootste risico, dan een concrete actie om het op te lossen.",
            "Vraag om bewijs wanneer succes niet inspecteerbaar is.",
            "Markeer elk punt expliciet als Blocker of Warning.",
            "Escaleer security-issues onmiddellijk, voor de afsluiting.",
        ],
        "tools": dict(_DEV_TEAM_TOOLS_ALL_ON),
        "model": "claude-opus-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-opus-4-6", "temperature": 0.25, "max_tokens": 2600, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#fb7185"},
        "knowledge_sources": [
            {"label": "Software testing", "url": "https://en.wikipedia.org/wiki/Software_testing", "note": "Basisreferentie voor regressie- en acceptatietesten."},
            {"label": "OWASP Top 10", "url": "https://owasp.org/Top10/", "note": "Snelle referentie voor security-risico's bij code-review."},
        ],
        "tags": ["critic", "default", "dev-team"],
        "builtin": True,
    },
    {
        "id": "de-developer",
        "name": "De Developper",
        "description": "Implementer in het Ouroboros-ontwikkelteam: vertaalt het bouwdoel naar concrete code-wijzigingen — files, symbols en diff-schetsen.",
        "role": "Ouroboros development engineer and code change author",
        "introduction": "Ik vertaal het doel naar een concrete code-wijziging die een uitvoerende agent kan runnen.",
        "system_prompt": (
            "Je bent De Developper van het Ouroboros-ontwikkelteam. Je enige taak: het bouwdoel omzetten naar een werkbare code-wijziging die een andere agent kan uitvoeren.\n"
            "Je denkt in files, functies, contracten en kleine diffs.\n\n"
            "Verplichte vorm voor ELKE bijdrage — als deze ontbreekt wordt je beurt door De Voorzitter teruggestuurd:\n"
            "- Minstens één concreet file path (bv. `src/cli.py`, `tests/test_engine.py`) — niet alleen een laagnaam.\n"
            "- Minstens één concreet symbol of function-naam (bv. `ChessGame.make_move`, `parse_move(uci: str) -> Move`).\n"
            "- Een korte schets (1-2 zinnen) van wat er in die file/symbol verandert.\n"
            "- Eén vervolgvraag aan De Tester of De Criticus die je beantwoord wil zien.\n"
            "Als je de bestaande codebase nog niet kent: noem dán toch een PROPOSED file path (waar de wijziging logischerwijs hoort) en zeg expliciet dat je hem eerst wil lezen via read_file of file_search.\n\n"
            "Voorbeeld van een goed antwoord:\n"
            "\"Voor het Ollama-koppeling-stuk maak ik `src/ollama_client.py` met `get_model_move(model: str, fen: str, max_retries: int = 3) -> str | None`. De functie POST't naar `http://localhost:11434/api/generate`, valideert het antwoord tegen `chess.Board.legal_moves` en geeft `None` bij uitputting. Vraag aan De Tester: hoe mock je de POST in `tests/test_ollama_client.py` deterministisch?\"\n\n"
            "Harde regels:\n"
            "- Citeer altijd de werkelijke file paths en symbol names. Vage verwijzingen ('de auth module') worden verworpen.\n"
            "- Als je de bestaande code niet kent, propose een aannemelijk pad EN stel een read_file-stap voor.\n"
            "- Stel nooit een refactor voor die het doel niet vereist.\n"
            "- Als De Criticus een reëel risico aanwijst, adresseer het in je volgende beurt — niet ontwijken.\n"
            "- Tools die je mag inzetten: read_file en file_search om de codebase te kennen; web_search voor framework/library docs; code_execution + local_shell + run_tests ALLEEN via de approval-gated agent-runtime.\n"
            "- Vermijd interne regiewoorden (spoor, deep think, acceptatie blijft, approvalpoort, bouwticket); begin niet met je eigen naam."
        ),
        "tone": "Pragmatisch, precies, gericht op uitvoerbare diffs",
        "language": "nl",
        "rules": [
            "Citeer altijd letterlijke file paths en symbol names; geen vage verwijzingen.",
            "Schets de implementatie kort, niet als volledige diff.",
            "Lees eerst de bestaande code voor je een refactor voorstelt.",
            "Adresseer Criticus-risico's in je volgende beurt; ontwijk ze niet.",
            "Geen executie buiten de approval-gated agent-runtime.",
        ],
        "tools": dict(_DEV_TEAM_TOOLS_ALL_ON),
        "model": "claude-sonnet-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-sonnet-4-6", "temperature": 0.3, "max_tokens": 2600, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#a3a8f0"},
        "knowledge_sources": [
            {"label": "Conventional Commits", "url": "https://www.conventionalcommits.org/", "note": "Concrete commit-conventie voor bouwprompts en kleine diffs."},
            {"label": "Twelve-Factor App", "url": "https://12factor.net/", "note": "Achtergrondnormen voor configuratie, omgeving en builds."},
        ],
        "tags": ["developer", "default", "dev-team"],
        "builtin": True,
    },
    {
        "id": "de-tester",
        "name": "De Tester",
        "description": "Verificatie-poort in het Ouroboros-ontwikkelteam: levert exacte testcommando's, verwachte signalen en rollbackroutes.",
        "role": "Ouroboros development verification gate",
        "introduction": "Ik maak elke wijziging bewijsbaar: exact testcommando, verwacht signaal en rollback.",
        "system_prompt": (
            "Je bent De Tester van het Ouroboros-ontwikkelteam. Je enige taak: elke wijziging bewijsbaar maken. Zonder jouw acceptatietest is de bouwprompt niet klaar.\n\n"
            "Jouw aanpak per beurt:\n"
            "1. Noem het exacte testcommando dat zal draaien (pytest -k ..., npm test --, cargo test ..., curl + jq, etc.).\n"
            "2. Noem het verwachte signaal: welke assertion slaagt, hoe ziet de output eruit, welke statuscode.\n"
            "3. Noem het faalsignaal: welke foutmelding of log-regel betekent dat de wijziging iets brak.\n"
            "4. Noem de rollback: welke commit, file of feature-flag te reverten als de test faalt.\n"
            "5. Als de wijziging moeilijk te testen is, vraag De Developper om de kleinste hook die het testbaar maakt.\n\n"
            "Harde regels:\n"
            "- Elke test moet reproduceerbaar zijn vanaf een schone state. 'Handmatig in de UI klikken' is geen test.\n"
            "- Als De Developper een wijziging voorstelt zonder helder acceptatiesignaal, vraag erom voor je akkoord geeft.\n"
            "- Onderscheid smoke tests (basis laad-check) van acceptance tests (bewijst het doel).\n"
            "- Voor UI-wijzigingen eis je een screenshot-test, DOM-assertion of end-to-end testcommando.\n"
            "- Vermijd interne regiewoorden (spoor, deep think, acceptatie blijft, approvalpoort, bouwticket); begin niet met je eigen naam."
        ),
        "tone": "Bewijsgericht, droog-precies, geen aanname zonder check",
        "language": "nl",
        "rules": [
            "Elke wijziging krijgt een exact testcommando + verwacht signaal + faalsignaal.",
            "Geen acceptatie zonder reproduceerbare test vanaf schone state.",
            "Onderscheid smoke test van acceptance test expliciet.",
            "UI-wijzigingen eisen een mechanische assertion, geen 'handmatig klikken'.",
        ],
        "tools": dict(_DEV_TEAM_TOOLS_ALL_ON),
        "model": "claude-sonnet-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-sonnet-4-6", "temperature": 0.2, "max_tokens": 2400, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#5dd5b2"},
        "knowledge_sources": [
            {"label": "pytest documentation", "url": "https://docs.pytest.org/", "note": "Naslag voor concrete pytest-acceptatietests en parametrisering."},
            {"label": "Testing Library principles", "url": "https://testing-library.com/docs/guiding-principles/", "note": "Naslag voor UI-tests die echt het gedrag valideren."},
        ],
        "tags": ["tester", "default", "dev-team"],
        "builtin": True,
    },
)
MAX_TEXT_CHARS = 16_000
MAX_UPLOAD_BYTES = 20_000_000
MAX_ATTACHMENT_CONTEXT_CHARS = 24_000
TEXT_ATTACHMENT_EXTENSIONS = {
    "txt",
    "md",
    "csv",
    "json",
    "yaml",
    "yml",
    "toml",
    "py",
    "ts",
    "tsx",
    "js",
    "jsx",
    "rs",
    "go",
    "java",
    "c",
    "cc",
    "cpp",
    "h",
    "hpp",
    "css",
    "html",
    "sql",
    "sh",
}
DOCUMENT_ATTACHMENT_EXTENSIONS = TEXT_ATTACHMENT_EXTENSIONS | {"pdf", "docx"}
IMAGE_ATTACHMENT_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
VISION_MODEL_MARKERS = ("llava", "bakllava", "moondream", "minicpm-v", "vision")

CLINE_ROOT = Path("/home/pwintri2/cline")
ALLOWED_CLINE_FILES: tuple[str, ...] = (
    "README.md",
    "README.marketplace.md",
    "docs/cline-overview.mdx",
    "docs/core-workflows/plan-and-act.mdx",
    "docs/core-workflows/task-management.mdx",
    "docs/core-workflows/working-with-files.mdx",
    "docs/core-workflows/checkpoints.mdx",
    "docs/features/subagents.mdx",
    "docs/customization/cline-rules.mdx",
    "docs/customization/hooks.mdx",
    "docs/mcp/mcp-overview.mdx",
    "docs/cli/cli-reference.mdx",
    "docs/cli/agent-teams.mdx",
    "docs/cli/connectors.mdx",
    "docs/sdk/overview.mdx",
    "package.json",
)

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(api[_-]?key|client[_-]?secret|secret|token|password|passwd|authorization|oauth)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:@\-]{8,}"
    ),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"\b(?:sk|ghp|gho|github_pat|xoxb|xoxp|xoxa|ya29)[-_A-Za-z0-9]{10,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
)

MEETING_FORBIDDEN_TOOL_MARKERS = (
    "cline",
    "shell",
    "safe_shell",
    "browser",
    "write",
    "apply_patch",
    "execute",
    "run_command",
    "run_tests",
    "roo_write",
    "roo_apply",
    "roo_execute",
)

MEETING_TYPE_ALIASES = {
    "team": "team",
    "team_meeting": "team",
    "teamvergadering": "team",
    "team vergadering": "team",
    "sprint": "sprint_planning",
    "sprint_planning": "sprint_planning",
    "sprint planning": "sprint_planning",
    "brainstorm": "brainstorm",
    "brainstormsessie": "brainstorm",
    "brainstorm sessie": "brainstorm",
    "development_team": "development_team",
    "development team": "development_team",
    "dev_team": "development_team",
    "dev-team": "development_team",
    "ontwikkelteam": "development_team",
    "ontwikkelteam-vergadering": "development_team",
}

MEETING_TYPE_LABELS = {
    "team": "Team vergadering",
    "sprint_planning": "Sprint planning",
    "brainstorm": "Brainstormsessie",
    "development_team": "Ontwikkelteam-vergadering",
}

DEV_TEAM_DEFAULT_PERSONA_IDS: tuple[str, ...] = (
    "dev-voorman",
    "dev-ontwerper",
    "dev-developper",
    "dev-tester",
    "dev-critikus",
)
GASTOWN_ROOT = Path(os.getenv("GASTOWN_ROOT", "/home/pwintri2/gastown"))
DEVTEAM_PLANNING_STRATEGIES = {"deterministic", "legacy-meeting"}
HIDDEN_DEVELOPMENT_PERSONA_IDS: frozenset[str] = frozenset(
    {
        "de-voorzitter",
        "de-ontwerper",
        "de-developer",
        "de-developper",
        "de-tester",
        "de-criticus",
        *DEV_TEAM_DEFAULT_PERSONA_IDS,
    }
)

CODING_MODEL_HINTS = {
    CHATGPT_CODEX_PROVIDER: (CHATGPT_CODEX_DEFAULT_MODEL, "gpt-5.1-codex"),
    "openai": ("gpt-5.3-codex", "gpt-5.4-mini"),
    "google": ("gemini-2.5-pro", "gemini-2.5-flash"),
    "ollama": ("devstral:latest", "deepseek-coder:latest", "codellama:13b"),
}


class OuroborosChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    system_prompt: Optional[str] = Field(default=None, max_length=MAX_TEXT_CHARS)
    persona_id: Optional[str] = Field(default=None, max_length=80)
    conversation_id: Optional[str] = Field(default=None, max_length=120)
    thread_id: Optional[str] = Field(default=None, max_length=120)
    approval: Optional[str] = Field(default=None, max_length=128)
    history: list[dict[str, Any]] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class PersonaRequest(BaseModel):
    id: Optional[str] = Field(default=None, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    role: str = Field(default="", max_length=240)
    introduction: str = Field(default="", max_length=1200)
    instructions: str = Field(default="", max_length=MAX_TEXT_CHARS)
    system_prompt: str = Field(default="", max_length=MAX_TEXT_CHARS)
    tone: str = Field(default="Grounded, practical, inspectable", max_length=240)
    language: str = Field(default="nl", max_length=40)
    rules: list[str] = Field(default_factory=list)
    tools: dict[str, bool] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    model: str = Field(default=DEFAULT_MODEL, max_length=160)
    model_settings: dict[str, Any] = Field(default_factory=dict)
    avatar: dict[str, Any] = Field(default_factory=dict)
    conversation_starters: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    knowledge_sources: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_files: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ConversationRequest(BaseModel):
    persona_id: str = Field(default="ouroboros", max_length=80)
    title: str = Field(default="New thread", max_length=160)


class MemoryRequest(BaseModel):
    persona_id: Optional[str] = Field(default=None, max_length=80)
    conversation_id: Optional[str] = Field(default=None, max_length=120)
    scope: str = Field(default="persona", max_length=40)
    content: str = Field(..., min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3)


class MeetingRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    meeting_type: str = Field(default="team", max_length=40)
    participants: list[str] = Field(default_factory=list)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    approval: Optional[str] = Field(default=None, max_length=128)
    tools: list[str] = Field(default_factory=list)
    allow_tools: bool = False


class MeetingSaveRequest(BaseModel):
    topic: str = Field(default="", max_length=MAX_TEXT_CHARS)
    meeting_type: str = Field(default="", max_length=40)
    frontend_id: Optional[str] = Field(default=None, max_length=120)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    agent_ids: list[str] = Field(default_factory=list)
    rounds: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = Field(default="", max_length=MAX_TEXT_CHARS)
    transcript: str = Field(default="", max_length=MAX_TEXT_CHARS * 2)
    status: str = Field(default="saved", max_length=40)


class DevelopmentTeamRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    persona_ids: list[str] = Field(default_factory=list)
    agent_ids: list[str] = Field(default_factory=list)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    approval: Optional[str] = Field(default=None, max_length=128)
    max_iterations: int = Field(default=3)
    # Optional list of {"question": "...", "answer": "..."} pairs from a preceding intake step.
    # When present, the development team meeting receives the original prompt plus the Q&A as
    # extra context so the four roles don't have to rediscover the user's intent.
    clarifications: list[dict[str, str]] = Field(default_factory=list)


class DevelopmentTeamIntakeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)


class DevelopmentTeamBuildRequest(BaseModel):
    """Build-modus: isolated development agents consume a formal build_plan and iterate to green."""

    build_plan: Optional[dict[str, Any]] = Field(default=None)
    build_prompt: Optional[str] = Field(default=None, max_length=MAX_TEXT_CHARS)
    persona_ids: list[str] = Field(default_factory=list)
    clarifications: list[dict[str, str]] = Field(default_factory=list)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    max_iterations: int = Field(default=4)
    min_iterations: int = Field(default=2)
    test_timeout_seconds: float = Field(default=120.0)
    llm_timeout_seconds: float = Field(default=90.0)
    approval: Optional[str] = Field(default=None, max_length=128)


def init_ouroboros_chat_routes(app: Any, service: "OuroborosChatService | None" = None) -> None:
    """Mount the standalone Ouroboros chat routes onto a FastAPI app."""

    if service is not None:
        app.state.ouroboros_chat_service = service
    app.include_router(ouroboros_chat_router)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or os.getenv("WINTRIP_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _default_data_dir() -> Path:
    configured = os.getenv("WINTRIP_OUROBOROS_CHAT_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (_workspace_root() / "data" / "ouroboros_chat").resolve()


def _default_persona() -> dict[str, Any]:
    return core_default_persona()


def _default_meeting_personas() -> list[dict[str, Any]]:
    personas: list[dict[str, Any]] = []
    for item in DEFAULT_MEETING_PERSONAS:
        persona = normalize_persona_payload(dict(item), previous={"builtin": True})
        persona["builtin"] = True
        persona["tags"] = list(item.get("tags", []))
        personas.append(persona)
    return personas


def _default_development_team_personas() -> list[dict[str, Any]]:
    """Return the fixed Development Team roles as non-Meeting agents."""
    from controller.dev_team_build import DEVELOPMENT_AGENT_ROLE_ORDER, default_development_team_agents

    agents = default_development_team_agents()
    personas: list[dict[str, Any]] = []
    for role in DEVELOPMENT_AGENT_ROLE_ORDER:
        agent = dict(agents[role])
        persona = normalize_persona_payload(
            {
                "id": agent.get("id") or f"dev-{role}",
                "name": agent.get("name") or role,
                "description": f"Vaste OUROBOROS DEVELOPMENT TEAM rol: {agent.get('role') or role}.",
                "role": agent.get("role") or role,
                "introduction": f"Ik werk alleen in OUROBOROS DEVELOPMENT TEAM als {agent.get('name') or role}.",
                "instructions": agent.get("system_prompt") or "",
                "system_prompt": agent.get("system_prompt") or "",
                "tone": "Kort, expliciet, overdraagbaar",
                "language": "nl",
                "rules": [
                    "Geen Meeting-persona context gebruiken.",
                    "Communiceer via expliciete handoff/mailerregels.",
                    "Werk alleen vanuit het formele build_plan.",
                ],
                "tools": {"web_search": False, "file_search": False, "code_execution": False, "local_shell": False},
                "tags": ["development-team-agent", role],
                "builtin": True,
            },
            previous={"builtin": True},
        )
        persona["builtin"] = True
        persona["development_team_only"] = True
        persona["development_role"] = role
        personas.append(persona)
    return personas


def _public_development_team_agents() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for persona in _default_development_team_personas():
        result.append(
            {
                "id": persona.get("id"),
                "name": persona.get("name"),
                "role": persona.get("development_role") or persona.get("role"),
                "label": persona.get("role"),
                "development_team_only": True,
            }
        )
    return result


def _development_team_planning_strategy() -> str:
    raw = os.getenv("WINTRIP_DEVTEAM_PLANNING_STRATEGY", "deterministic")
    value = str(raw or "").strip().lower().replace("_", "-")
    aliases = {
        "fast": "deterministic",
        "scripted": "deterministic",
        "no-llm": "deterministic",
        "meeting": "legacy-meeting",
        "full": "legacy-meeting",
        "llm": "legacy-meeting",
        "legacy": "legacy-meeting",
    }
    value = aliases.get(value, value)
    return value if value in DEVTEAM_PLANNING_STRATEGIES else "deterministic"


def _gastown_agent_message(
    *,
    mode: str,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    next_action: str,
) -> str:
    clean_mode = mode if mode in {"nudge", "mail", "handoff"} else "nudge"
    return (
        f"MODE: {clean_mode}\n"
        f"FROM: {sender}\n"
        f"TO: {recipient}\n"
        f"SUBJECT: {_clip_text(subject, 160)}\n"
        f"BODY:\n{_clip_text(body, 1800)}\n"
        f"NEXT: {_clip_text(next_action, 500)}\n"
        f"SOURCE: {GASTOWN_ROOT}"
    )


def _development_team_seed_plan(topic: str) -> dict[str, Any]:
    title = _clip_text(topic, 160) or "Ouroboros build"
    lower = topic.lower()
    components: list[dict[str, str]] = [{"name": "implementation", "description": title}]
    if any(marker in lower for marker in ("ui", "frontend", "scherm", "knop", "venster", "tauri")):
        components.append({"name": "ui", "description": "Maak de zichtbare workflow concreet en testbaar."})
    if any(marker in lower for marker in ("api", "backend", "endpoint", "route")):
        components.append({"name": "backend", "description": "Werk de backend-route of service met duidelijke input/output uit."})
    tests = ["Draai het kleinste relevante testcommando en verwacht exitcode 0."]
    if "python" in lower or "pytest" in lower:
        tests = ["python -m pytest -q"]
    elif "npm" in lower or "react" in lower or "tauri" in lower or "frontend" in lower:
        tests = ["npm test -- --runInBand of het lokale project-equivalent; verwacht exitcode 0."]
    return _normalize_build_plan(
        {
            "title": title,
            "goals": [topic],
            "components": components,
            "tests": tests,
            "constraints": [
                "Geen automatische externe acties zonder expliciet Akkoord.",
                "Meeting-persona's blijven gescheiden van OUROBOROS DEVELOPMENT TEAM.",
                "Ondersteunende rollen communiceren via Gas Town MODE: nudge/mail/handoff.",
            ],
        },
        fallback_title=title,
    )


def _safe_slug(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-").lower()
    return (text[:80] or fallback).strip(".-") or fallback


def _clip_text(value: Any, limit: int = 1200) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    return text[:limit]


def _natural_first_letter(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


# Markers that identify a TRULY small local model (≤ ~3B parameters or known weak at long-form
# structured output). When detected, the meeting flow falls back to compact prompts so the
# conversation stays on topic and the deterministic compositor takes over the structural work.
# 7B+ models (codellama, gemma:7b, ouroboros:latest etc.) handle the rich AgenK-style prompts
# fine; we only reduce when the model genuinely can't track them.
_LIGHT_MODEL_MARKERS: tuple[str, ...] = (
    "llama:3b",
    "llama3:3b",
    "llama3:1b",
    "llama3.1:3b",
    "llama3.2:1b",
    "llama3.2:3b",
    "llama2:3b",
    "llama2:1b",
    "phi3",
    "phi-3",
    "phi:3",
    "phi3:mini",
    "tinyllama",
    "qwen:1.5b",
    "qwen2:1.5b",
    "qwen2.5:1.5b",
    "gemma:2b",
    "gemma2:2b",
    "deepseek:1.3b",
    "deepseek-coder:1.3b",
)


def _is_light_model(provider: Any, model: Any) -> bool:
    text = f"{str(provider or '').lower()} {str(model or '').lower()}"
    return any(marker in text for marker in _LIGHT_MODEL_MARKERS)


def _parse_intake_response(content: Any) -> dict[str, Any]:
    """Parse the chair's intake JSON response with graceful fallbacks.

    Many small models return JSON inside markdown fences or with extra prose. This
    helper extracts the JSON object if it can find one, validates the shape, and
    falls back to a heuristic question-mark scan if the response isn't parseable.
    """
    text = str(content or "").strip()
    if not text:
        return {"needs_clarification": False, "questions": []}
    candidates: list[str] = [text]
    # Strip a markdown code fence if present.
    if text.startswith("```"):
        without_fence = text[3:]
        if without_fence.lower().startswith("json"):
            without_fence = without_fence[4:]
        if without_fence.endswith("```"):
            without_fence = without_fence[:-3]
        candidates.insert(0, without_fence.strip())
    # Try to slice from the first '{' to the matching '}' — handles preamble like
    # "Hier is mijn JSON: {...}".
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.insert(0, text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        needs = bool(parsed.get("needs_clarification"))
        raw_questions = parsed.get("questions") or []
        if isinstance(raw_questions, list):
            questions = [str(q).strip() for q in raw_questions if str(q).strip()]
        else:
            questions = []
        if not questions:
            needs = False
        return {"needs_clarification": needs, "questions": questions[:4]}

    # Heuristic fallback — pick the lines that end with a question mark.
    fallback_questions = []
    for line in text.splitlines():
        line = line.strip(" -*•\"'")
        # Ignore lines that look like code or json
        if line.endswith("?") and len(line) > 6 and "{" not in line and "}" not in line and "import " not in line and "def " not in line:
            fallback_questions.append(line)
            
    return {
        "needs_clarification": bool(fallback_questions),
        "questions": fallback_questions[:4],
    }


def _development_team_intake_timeout_seconds() -> float:
    raw = os.getenv("WINTRIP_DEVTEAM_INTAKE_TIMEOUT", "8")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 8.0
    return max(0.25, min(value, 30.0))


def _fallback_development_team_intake_questions(prompt: Any) -> list[str]:
    clean_prompt = " ".join(str(prompt or "").split())
    lower = clean_prompt.lower()
    looks_like_new_app = any(
        marker in lower
        for marker in (
            "maak ",
            "bouw ",
            "ontwikkel ",
            "app",
            "applicatie",
            "programma",
            "tool",
            "site",
            "website",
        )
    )
    directory_question = (
        "In welke specifieke directory moet dit worden opgeslagen?"
        if looks_like_new_app
        else "Welke bestaande directory of repo moet hiervoor gebruikt worden?"
    )
    return [
        "Wat is de kleinste scope die in de eerste werkende versie af moet zijn?",
        "Welke interface verwacht je: web, desktop, CLI of alleen backend?",
        "Welk acceptatiesignaal bewijst dat de build klaar is?",
        directory_question,
    ]


_MEETING_META_PATTERNS: tuple[tuple[Any, str], ...] = ()


def _strip_meeting_meta_language(content: Any, *, persona_name: str = "") -> str:
    """Post-process visible turn content so internal meeting labels do not leak into deelnemerbijdragen.

    This is a safety net: deterministic fallbacks already avoid these phrases, but an LLM may still
    echo them. The replacements keep meaning but remove the meta-vocabulary.
    """
    text = str(content or "")
    if not text:
        return ""
    import re as _re

    global _MEETING_META_PATTERNS
    if not _MEETING_META_PATTERNS:
        _MEETING_META_PATTERNS = (
            (_re.compile(r"(?i)\bkiest\s+spoor\s+([^.:\n]+?)([.:\n]|$)"), r"stelt voor om met \1 te beginnen\2"),
            (_re.compile(r"(?i)\bverdiept\s+spoor\s+([^.:\n]+?)([.:\n]|$)"), r"verdiept \1\2"),
            (_re.compile(r"(?i)\bmaakt\s+spoor\s+([^.:\n]+?)\s+patchbaar"), r"maakt \1 concreet"),
            (_re.compile(r"(?i)\btoetst\s+spoor\s+([^.:\n]+?)([.:\n]|$)"), r"toetst \1\2"),
            (_re.compile(r"(?i)\bhet\s+spoor\s+"), ""),
            (_re.compile(r"(?i)\bspoor\s+([A-Za-z0-9_-]+)"), r"\1"),
            (_re.compile(r"(?i)\bDeep\s+search\s+van\s+[^:]+:\s*"), ""),
            (_re.compile(r"(?i)\bDeep\s+think\s+van\s+[^:]+:\s*"), ""),
            (_re.compile(r"(?i)\bDeep\s+search(?:\s+vanuit\s+[^:]+)?:\s*"), ""),
            (_re.compile(r"(?i)\bDeep\s+think(?:\s+vanuit\s+[^:]+)?:\s*"), ""),
            (_re.compile(r"(?i)\bOplossing-dive\s+van\s+[^:]+:\s*"), ""),
            (_re.compile(r"(?i)\bAcceptatie\s+blijft:\s*"), "De toets blijft hetzelfde: "),
            (_re.compile(r"(?i)\bBewijs\s+dat\s+ik\s+wil\s+zien:\s*"), "Wat ik wil zien: "),
            (_re.compile(r"(?i)\bApprovalpoort:\s*"), ""),
            (_re.compile(r"(?i)\bApprovalpoort\b"), "Akkoord-grens"),
            (_re.compile(r"(?i)\bBouwticket:\s*"), "Mijn voorstel: "),
            (_re.compile(r"(?i)\bpatchbaar\s+experiment\b"), "klein toetsbaar experiment"),
            (_re.compile(r"(?i)\bde\s+volgende\s+spreker\s+verdiept\s+zijn\s+eigen\s+spoor\b"), "de volgende spreker gaat dieper in op zijn eigen laag"),
        )

    for pattern, replacement in _MEETING_META_PATTERNS:
        text = pattern.sub(replacement, text)
    text = _re.sub(r"\s{2,}", " ", text).strip()

    name = (persona_name or "").strip()
    if name:
        leading = _re.match(rf"^\s*{_re.escape(name)}\b[ ,:–-]+", text)
        if leading:
            remainder = text[leading.end():].lstrip()
            if remainder:
                text = remainder[0].upper() + remainder[1:]
    return text


def _attachment_extension(path_or_name: Any) -> str:
    name = str(path_or_name or "").lower().split("?", 1)[0]
    return name.rsplit(".", 1)[-1] if "." in name else ""


def _attachment_kind(path_or_name: Any) -> str:
    ext = _attachment_extension(path_or_name)
    if ext in IMAGE_ATTACHMENT_EXTENSIONS:
        return "image"
    if ext in DOCUMENT_ATTACHMENT_EXTENSIONS:
        return "document"
    return "unsupported"


def _model_supports_images(model: str) -> bool:
    lowered = str(model or "").lower()
    return any(marker in lowered for marker in VISION_MODEL_MARKERS)


def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in SECRET_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_secret_like(key) or _contains_secret_like(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_secret_like(item) for item in value)
    return False


def _redact_secret_like(text: str) -> str:
    clean = str(text or "")
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def _read_text_limited(path: Path, limit: int = 80_000) -> str:
    with path.open("rb") as handle:
        data = handle.read(limit)
    return data.decode("utf-8", errors="replace")


def _extract_attachment_text(path: Path, limit: int = MAX_ATTACHMENT_CONTEXT_CHARS) -> str:
    ext = _attachment_extension(path.name)
    try:
        if ext in TEXT_ATTACHMENT_EXTENSIONS:
            return _read_text_limited(path, limit=limit)
        if ext == "pdf":
            import PyPDF2

            pages: list[str] = []
            with path.open("rb") as handle:
                reader = PyPDF2.PdfReader(handle)
                for page in reader.pages[:12]:
                    page_text = page.extract_text() or ""
                    if page_text:
                        pages.append(page_text)
                    if len("\n".join(pages)) >= limit:
                        break
            return "\n".join(pages)[:limit]
        if ext == "docx":
            import docx

            doc = docx.Document(str(path))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)[:limit]
    except Exception as exc:
        return f"[Attachment read error for {path.name}: {exc}]"
    return ""


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    if relative_path not in ALLOWED_CLINE_FILES:
        raise ValueError(f"Cline path is not allowlisted: {relative_path}")
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / relative_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Cline path escapes root: {relative_path}") from exc
    return candidate


def _extract_headings(text: str, limit: int = 8) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                headings.append(_redact_secret_like(heading)[:160])
        if len(headings) >= limit:
            break
    return headings


def _excerpt(text: str, limit: int = 500) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("---", "import ", "export ")):
            continue
        lines.append(stripped)
        if len(" ".join(lines)) >= limit:
            break
    return _redact_secret_like(" ".join(lines))[:limit]


def _history_for_ollama(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    for item in history[-20:]:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "")
        if role not in {"system", "user", "assistant", "tool"} or not content:
            continue
        clean.append({"role": role, "content": content[:MAX_TEXT_CHARS]})
    return clean


def _slug_list(values: list[str], limit: int = 12) -> list[str]:
    result: list[str] = []
    for value in values[:limit]:
        slug = _safe_slug(value, fallback="")
        if slug:
            result.append(slug)
    return result


def _dedupe_strings(values: list[Any] | tuple[Any, ...], *, fallback: tuple[str, ...] = ()) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in [*values, *fallback]:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _normalize_build_plan(value: dict[str, Any], *, fallback_title: Any = "") -> dict[str, Any]:
    def _string_list(raw: Any) -> list[str]:
        if isinstance(raw, list):
            return _dedupe_strings([_clip_text(item, 500) for item in raw if str(item or "").strip()])
        if str(raw or "").strip():
            return [_clip_text(raw, 500)]
        return []

    def _component_list(raw: Any) -> list[dict[str, str]]:
        components: list[dict[str, str]] = []
        if isinstance(raw, list):
            for index, item in enumerate(raw[:12], start=1):
                if isinstance(item, dict):
                    name = _clip_text(item.get("name") or item.get("path") or f"component_{index}", 120)
                    description = _clip_text(item.get("description") or item.get("summary") or name, 400)
                else:
                    name = _clip_text(item, 120)
                    description = name
                if name:
                    components.append({"name": name, "description": description})
        return components

    title = _clip_text(value.get("title") or fallback_title or "Ouroboros build", 160)
    goals = _string_list(value.get("goals")) or [title]
    components = _component_list(value.get("components")) or [{"name": "implementation", "description": title}]
    tests = _string_list(value.get("tests")) or ["Draai het kleinste relevante testcommando en verwacht exitcode 0."]
    constraints = _string_list(value.get("constraints")) or ["Geen automatische externe acties zonder expliciet Akkoord."]
    return {
        "title": title,
        "goals": goals[:8],
        "components": components[:12],
        "tests": tests[:8],
        "constraints": constraints[:8],
    }


def _build_plan_from_request(request: "DevelopmentTeamBuildRequest") -> dict[str, Any]:
    raw_plan = request.build_plan if isinstance(request.build_plan, dict) else None
    if raw_plan is not None:
        return _normalize_build_plan(raw_plan, fallback_title=(request.build_prompt or ""))
    raw_prompt = str(request.build_prompt or "").strip()
    if not raw_prompt:
        raise ValueError("Development build requires a formal build_plan or a non-empty build_prompt.")
    start = raw_prompt.find("{")
    end = raw_prompt.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(raw_prompt[start : end + 1])
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return _normalize_build_plan(parsed, fallback_title=raw_prompt[:160])
    return _normalize_build_plan({"title": raw_prompt[:160], "goals": [raw_prompt]}, fallback_title=raw_prompt[:160])


def _safe_attachment_path(value: Any) -> Path | None:
    raw = ""
    if isinstance(value, dict):
        raw = str(value.get("path") or value.get("file_path") or "")
    else:
        raw = str(value or "")
    if not raw.strip():
        return None
    path = Path(raw.strip()).expanduser()
    try:
        return path.resolve()
    except Exception:
        return None


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    dumper = getattr(model, "model_dump", None)
    if callable(dumper):
        return dict(dumper())
    return dict(model.dict())


def _normalize_meeting_type(value: Any) -> str:
    text = str(value or "team").strip().lower().replace("-", "_")
    return MEETING_TYPE_ALIASES.get(text, MEETING_TYPE_ALIASES.get(text.replace("_", " "), "team"))


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _matches_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _classify_topic_intent(topic: Any) -> str:
    text = re.sub(r"\s+", " ", str(topic or "").strip().lower())
    if not text:
        return "vraag"

    hard_incident_patterns = (
        r"\bik krijg\b.*\b(error|fout|load failed|exception)\b",
        r"\bik kan\b.*\bniet\b.*\b(starten|openen|laden|gebruiken|bereiken)\b",
        r"\b(is|zijn|blijft|blijven)\s+nu\s+(offline|kapot|stuk|rood|vast)\b",
        r"\b(doet|werkt|laadt|start)\b.*\bniet\b",
    )
    incident_phrases = (
        "load failed bij",
        "backend is offline",
        "backend offline",
        "crasht",
        "crash",
        "foutmelding",
        "error bij",
        "exception",
        "niet starten",
        "niet laden",
        "loopt vast",
        "hangt vast",
    )
    assignment_phrases = (
        "hoe programmeren we",
        "programmeer",
        "programmeren",
        "implementeer",
        "implementeren",
        "bouw",
        "bouwen",
        "maak",
        "zorg dat",
        "kan je",
        "kun je",
        "wil je",
        "ik wil dat",
        "moet een app worden",
        "verbeter",
        "voorkom",
        "monitor",
        "maak dit",
        "pas aan",
    )
    idea_phrases = (
        "ik heb een idee",
        "idee:",
        "wat als",
        "misschien kunnen",
        "concept",
        "verken",
        "brainstorm over",
        "stel je voor",
        "zou het kunnen",
        "prototype",
    )
    question_patterns = (
        r"^(wat is|wat zijn|waarom|hoe werkt|welk verschil|wat is het verschil)\b",
    )

    if _matches_pattern(text, hard_incident_patterns) or _contains_phrase(text, incident_phrases):
        return "storing"
    if _contains_phrase(text, assignment_phrases):
        return "opdracht"
    if _contains_phrase(text, idea_phrases):
        return "idee"
    if _matches_pattern(text, question_patterns):
        return "vraag"
    if text.endswith("?") and not _contains_phrase(text, ("bouw", "maak", "zorg dat", "programmeer")):
        return "vraag"
    return "opdracht" if _contains_phrase(text, ("moet", "nodig", "doel", "route")) else "vraag"


def _topic_intent_label(intent: str) -> str:
    labels = {
        "opdracht": "Opdracht / implementatie",
        "storing": "Storing / incident",
        "idee": "Idee / verkenning",
        "vraag": "Vraag / uitleg",
    }
    return labels.get(intent, labels["vraag"])


def _topic_intent_contract(intent: str) -> str:
    if intent == "opdracht":
        return (
            "ONDERWERPSOORT: dit is een opdracht of implementatievraag. Behandel het als iets dat gebouwd, ontworpen, "
            "gepland of getest moet worden; spreek niet alsof er al een actuele storing is."
        )
    if intent == "storing":
        return (
            "ONDERWERPSOORT: dit is een storing of incident. Eerst diagnose, oorzaak, herstelpad en bewijs; "
            "pas daarna structurele verbetering."
        )
    if intent == "idee":
        return (
            "ONDERWERPSOORT: dit is een idee of verkenning. Vergroot de oplossingsruimte met waarde, varianten, "
            "prototype, risico en klein experiment; maak er nog geen incident van."
        )
    return (
        "ONDERWERPSOORT: dit is een vraag of uitlegverzoek. Verhelder begrippen, verschillen, voorbeelden en gevolgen "
        "voordat je een bouwplan of diagnose maakt."
    )


def _chatgpt_copilot_token_file() -> Path:
    configured = os.getenv("CHATGPT_COPILOT_TOKEN_FILE") or os.getenv("WINTRIP_CHATGPT_CODEX_TOKEN_FILE")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".chatgpt-copilot" / "oauth-tokens.json").resolve()


def _goose_chatgpt_codex_token_file() -> Path:
    configured = os.getenv("GOOSE_CHATGPT_CODEX_TOKEN_FILE") or os.getenv("WINTRIP_GOOSE_CHATGPT_CODEX_TOKEN_FILE")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".config" / "goose" / "chatgpt_codex" / "tokens.json").resolve()


def _codex_auth_file() -> Path:
    configured = os.getenv("CODEX_AUTH_FILE") or os.getenv("WINTRIP_CODEX_AUTH_FILE")
    if configured:
        return Path(configured).expanduser().resolve()
    codex_home = os.getenv("CODEX_HOME") or os.getenv("WINTRIP_CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return (root / "auth.json").resolve()


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_secret_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _normalize_chatgpt_codex_token(raw: dict[str, Any]) -> dict[str, Any]:
    token = {
        "provider": "chatgpt",
        "accessToken": str(raw.get("accessToken") or raw.get("access_token") or "").strip(),
        "refreshToken": str(raw.get("refreshToken") or raw.get("refresh_token") or "").strip(),
        "idToken": str(raw.get("idToken") or raw.get("id_token") or "").strip(),
        "expiresAt": raw.get("expiresAt") or raw.get("expires_at") or "",
        "accountId": str(raw.get("accountId") or raw.get("account_id") or "").strip(),
    }
    if not (token["accessToken"] or token["refreshToken"]):
        return {}
    return {key: value for key, value in token.items() if value not in ("", None)}


def _load_chatgpt_copilot_token() -> dict[str, Any]:
    path = _chatgpt_copilot_token_file()
    data = _load_json_dict(path)
    token = data.get("chatgpt")
    return _normalize_chatgpt_codex_token(token) if isinstance(token, dict) else {}


def _load_goose_chatgpt_codex_token() -> dict[str, Any]:
    return _normalize_chatgpt_codex_token(_load_json_dict(_goose_chatgpt_codex_token_file()))


def _load_codex_auth_token() -> dict[str, Any]:
    data = _load_json_dict(_codex_auth_file())
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return {}
    auth_mode = str(data.get("auth_mode") or "").strip().lower()
    if auth_mode and auth_mode != "chatgpt":
        return {}
    return _normalize_chatgpt_codex_token(tokens)


def _save_chatgpt_copilot_token(token: dict[str, Any]) -> None:
    path = _chatgpt_copilot_token_file()
    data = _load_json_dict(path)
    data["chatgpt"] = {**token, "provider": "chatgpt"}
    _write_secret_json(path, data)


def _timestamp_to_utc_iso(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _chatgpt_token_access(token: dict[str, Any]) -> str:
    return str(token.get("accessToken") or token.get("access_token") or "").strip()


def _chatgpt_token_refresh(token: dict[str, Any]) -> str:
    return str(token.get("refreshToken") or token.get("refresh_token") or "").strip()


def _chatgpt_token_id(token: dict[str, Any]) -> str:
    return str(token.get("idToken") or token.get("id_token") or "").strip()


def _jwt_payload(access_token: str) -> dict[str, Any]:
    try:
        parts = str(access_token or "").split(".")
        if len(parts) != 3:
            return {}
        payload_part = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _token_expiry_seconds(token: dict[str, Any]) -> int:
    raw = token.get("expiresAt") or token.get("expires_at") or 0
    value = 0
    if isinstance(raw, str):
        text = raw.strip()
        if text:
            try:
                value = int(float(text))
            except ValueError:
                try:
                    value = int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
                except ValueError:
                    value = 0
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
    if not value:
        payload = _jwt_payload(_chatgpt_token_access(token))
        try:
            value = int(payload.get("exp") or 0)
        except (TypeError, ValueError):
            value = 0
    return value // 1000 if value > 10_000_000_000 else value


def _token_has_time_left(token: dict[str, Any], leeway_seconds: int = 300) -> bool:
    expires_at = _token_expiry_seconds(token)
    return not expires_at or time.time() < (expires_at - leeway_seconds)


def _chatgpt_account_id_from_jwt(access_token: str) -> str:
    payload = _jwt_payload(access_token)
    account = payload.get("https://api.openai.com/auth") if isinstance(payload, dict) else {}
    if isinstance(account, dict):
        return str(account.get("chatgpt_account_id") or "")
    return ""


def _chatgpt_token_account_id(token: dict[str, Any]) -> str:
    explicit = str(token.get("accountId") or token.get("account_id") or "").strip()
    return explicit or _chatgpt_account_id_from_jwt(_chatgpt_token_access(token))


def _save_goose_chatgpt_codex_token(token: dict[str, Any]) -> None:
    path = _goose_chatgpt_codex_token_file()
    data = _load_json_dict(path)
    access_token = _chatgpt_token_access(token)
    refresh_token = _chatgpt_token_refresh(token)
    id_token = _chatgpt_token_id(token)
    if access_token:
        data["access_token"] = access_token
    if refresh_token:
        data["refresh_token"] = refresh_token
    if id_token:
        data["id_token"] = id_token
    expires_at = _token_expiry_seconds(token)
    if expires_at:
        data["expires_at"] = _timestamp_to_utc_iso(expires_at)
    account_id = _chatgpt_token_account_id(token)
    if account_id:
        data["account_id"] = account_id
    _write_secret_json(path, data)


def _save_codex_auth_token(token: dict[str, Any]) -> None:
    path = _codex_auth_file()
    data = _load_json_dict(path)
    data["auth_mode"] = "chatgpt"
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    access_token = _chatgpt_token_access(token)
    refresh_token = _chatgpt_token_refresh(token)
    id_token = _chatgpt_token_id(token)
    if access_token:
        tokens["access_token"] = access_token
    if refresh_token:
        tokens["refresh_token"] = refresh_token
    if id_token:
        tokens["id_token"] = id_token
    account_id = _chatgpt_token_account_id(token)
    if account_id:
        tokens["account_id"] = account_id
    data["tokens"] = tokens
    data["last_refresh"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _write_secret_json(path, data)


def _chatgpt_codex_token_sources() -> list[dict[str, Any]]:
    return [
        {
            "id": "chatgpt-copilot",
            "auth_mode": "oauth_shared_file",
            "path": _chatgpt_copilot_token_file(),
            "token": _load_chatgpt_copilot_token(),
            "save": _save_chatgpt_copilot_token,
        },
        {
            "id": "goose:chatgpt_codex",
            "auth_mode": "oauth_goose",
            "path": _goose_chatgpt_codex_token_file(),
            "token": _load_goose_chatgpt_codex_token(),
            "save": _save_goose_chatgpt_codex_token,
        },
        {
            "id": "codex:auth.json",
            "auth_mode": "oauth_codex",
            "path": _codex_auth_file(),
            "token": _load_codex_auth_token(),
            "save": _save_codex_auth_token,
        },
    ]


def _chatgpt_codex_token_usable(token: dict[str, Any]) -> bool:
    return bool((_chatgpt_token_access(token) and _token_has_time_left(token)) or _chatgpt_token_refresh(token))


def _chatgpt_codex_status(openai_subscription: dict[str, Any] | None = None) -> dict[str, Any]:
    sources = _chatgpt_codex_token_sources()
    usable_source = next((source for source in sources if _chatgpt_codex_token_usable(source.get("token", {}))), None)
    present_source = next((source for source in sources if source.get("token")), None)
    selected_source = usable_source or present_source or sources[0]
    token = selected_source.get("token", {}) if isinstance(selected_source.get("token"), dict) else {}
    expires_at = _token_expiry_seconds(token)
    has_refresh = any(bool(_chatgpt_token_refresh(source.get("token", {}))) for source in sources)
    shared_usable = bool(usable_source)
    source = str(selected_source.get("id") or "missing") if (shared_usable or present_source) else "missing"
    auth_mode = str(selected_source.get("auth_mode") or "oauth_shared_file")
    status = "configured" if shared_usable else "missing_token"

    subscription = openai_subscription or {}
    sub_active = bool(subscription.get("active") and not subscription.get("expired"))
    sub_oauth_ready = bool(
        sub_active
        and subscription.get("has_credential")
        and str(subscription.get("auth_mode") or "") == "oauth_refresh_token"
    )
    if not shared_usable and sub_oauth_ready:
        source = "subscription:oauth_refresh_token"
        auth_mode = "oauth_refresh_token"
        status = "configured"
    token_sources = [
        {
            "id": str(item.get("id") or ""),
            "auth_mode": str(item.get("auth_mode") or ""),
            "path": str(item.get("path") or ""),
            "present": bool(item.get("token")),
            "configured": _chatgpt_codex_token_usable(item.get("token", {})),
        }
        for item in sources
    ]

    return {
        "configured": bool(shared_usable or sub_oauth_ready),
        "direct_chat": bool(shared_usable or sub_oauth_ready),
        "status": status,
        "auth_mode": auth_mode,
        "key_source": source,
        "token_file": str(selected_source.get("path") or _chatgpt_copilot_token_file()),
        "token_file_present": bool(present_source),
        "token_sources": token_sources,
        "expires_at": _timestamp_to_utc_iso(expires_at) if expires_at else "",
        "expired": bool(expires_at and time.time() >= expires_at),
        "has_refresh_token": has_refresh,
    }


class _SimpleHTTPResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self) -> Any:
        return json.loads(self.text or "{}")


def _http_post(
    url: str,
    *,
    headers: dict[str, str],
    data: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> Any:
    try:
        import requests

        kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
        if json_body is not None:
            kwargs["json"] = json_body
        else:
            kwargs["data"] = data or {}
        return requests.post(url, **kwargs)
    except ModuleNotFoundError:
        pass

    import urllib.error
    import urllib.parse
    import urllib.request

    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **headers}
    else:
        body = urllib.parse.urlencode(data or {}).encode("utf-8")
        request_headers = {"Content-Type": "application/x-www-form-urlencoded", **headers}
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _SimpleHTTPResponse(response.getcode(), response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return _SimpleHTTPResponse(exc.code, exc.read().decode("utf-8", errors="replace"))


class PersonaStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (_default_data_dir() / "personas.json")

    def list_personas(self) -> list[dict[str, Any]]:
        return list(self._load().get("personas", []))

    def get(self, persona_id: str | None) -> dict[str, Any] | None:
        if not persona_id:
            return None
        clean_id = _safe_slug(persona_id)
        for persona in self.list_personas():
            if persona.get("id") == clean_id:
                return dict(persona)
        return None

    def upsert(self, request: PersonaRequest) -> dict[str, Any]:
        payload = _model_to_dict(request)
        if _contains_secret_like(payload):
            raise ValueError("Persona content appears to contain a secret, token, password, or bearer credential.")

        clean_id = _safe_slug(request.id or request.name, fallback=f"persona-{uuid.uuid4().hex[:8]}")
        data = self._load()
        existing = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        previous = existing.get(clean_id, {})
        persona = normalize_persona_payload({**payload, "id": clean_id}, previous=previous)
        persona["tags"] = _slug_list(request.tags)
        existing[clean_id] = persona
        self._save({"version": 1, "personas": sorted(existing.values(), key=lambda item: item["id"])})
        return persona

    def duplicate(self, persona_id: str) -> dict[str, Any]:
        source = self.get(persona_id)
        if source is None:
            raise KeyError(_safe_slug(persona_id))
        payload = dict(source)
        payload["id"] = f"{source.get('id', 'persona')}-copy-{uuid.uuid4().hex[:4]}"
        payload["name"] = f"{source.get('name', 'Persona')} Copy"
        payload["builtin"] = False
        normalized = normalize_persona_payload(payload, previous={})
        data = self._load()
        personas = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        personas[normalized["id"]] = normalized
        self._save({"version": 1, "personas": sorted(personas.values(), key=lambda item: item["id"])})
        return normalized

    def import_persona(self, payload: dict[str, Any]) -> dict[str, Any]:
        if _contains_secret_like(payload):
            raise ValueError("Persona import appears to contain a secret, token, password, or bearer credential.")
        normalized = normalize_persona_payload(payload, previous={})
        data = self._load()
        personas = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        personas[normalized["id"]] = normalized
        self._save({"version": 1, "personas": sorted(personas.values(), key=lambda item: item["id"])})
        return normalized

    def patch(self, persona_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if _contains_secret_like(payload):
            raise ValueError("Persona patch appears to contain a secret, token, password, or bearer credential.")
        clean_id = _safe_slug(persona_id)
        data = self._load()
        personas = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        previous = personas.get(clean_id)
        if previous is None:
            raise KeyError(clean_id)
        normalized = normalize_persona_payload({**previous, **payload, "id": clean_id}, previous=previous)
        personas[clean_id] = normalized
        self._save({"version": 1, "personas": sorted(personas.values(), key=lambda item: item["id"])})
        return normalized

    def archive(self, persona_id: str, *, hard: bool = False) -> dict[str, Any]:
        clean_id = _safe_slug(persona_id)
        data = self._load()
        personas = [dict(item) for item in data.get("personas", []) if isinstance(item, dict)]
        for index, persona in enumerate(personas):
            if persona.get("id") != clean_id:
                continue
            if hard:
                removed = personas.pop(index)
                self._save({"version": 1, "personas": personas or [_default_persona()]})
                return {"status": "deleted", "persona": removed}
            persona["archived"] = True
            persona["updated_at"] = _now_iso()
            personas[index] = persona
            self._save({"version": 1, "personas": personas})
            return {"status": "archived", "persona": persona}
        raise KeyError(clean_id)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "personas": self._with_builtin_personas([_default_persona()])}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Could not read persona store: {exc}") from exc
        personas = data.get("personas") if isinstance(data, dict) else None
        if not isinstance(personas, list):
            return {"version": 1, "personas": [_default_persona()]}
        safe_personas: list[dict[str, Any]] = []
        for item in personas:
            if isinstance(item, dict) and item.get("id") and not _contains_secret_like(item):
                normalized = normalize_persona_payload(dict(item), previous=dict(item))
                if isinstance(item.get("tags"), list):
                    normalized["tags"] = _slug_list([str(tag) for tag in item.get("tags", [])])
                if item.get("updated_at"):
                    normalized["updated_at"] = str(item.get("updated_at"))
                safe_personas.append(normalized)
        if not safe_personas:
            safe_personas.append(_default_persona())
        return {"version": 1, "personas": self._with_builtin_personas(safe_personas)}

    # Persona IDs whose system_prompt/tools/rules should always reflect the latest builtin
    # default. These are core meeting roles that are not user-customizable through the UI,
    # so on every startup we refresh them in-place to the newest definition.
    _ALWAYS_REFRESH_BUILTIN_IDS: tuple[str, ...] = (
        "de-voorzitter",
        "de-criticus",
        "de-developer",
        "de-tester",
    )

    # Fields that the dev-team force-refresh overwrites with the latest builtin definition.
    # Everything else (model_settings, knowledge_sources, avatar, archived, created_at, ...)
    # is preserved from the on-disk persona so user customisation through the UI survives.
    _BUILTIN_REFRESH_FIELDS: tuple[str, ...] = (
        "name",
        "description",
        "role",
        "introduction",
        "instructions",
        "system_prompt",
        "tone",
        "language",
        "rules",
        "tools",
        "tags",
    )

    def _with_builtin_personas(self, personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {str(item.get("id")): dict(item) for item in personas if item.get("id")}
        for persona in _default_meeting_personas():
            if persona["id"] not in by_id:
                by_id[persona["id"]] = persona
            elif by_id[persona["id"]].get("builtin"):
                existing = by_id[persona["id"]]
                if persona["id"] in self._ALWAYS_REFRESH_BUILTIN_IDS:
                    # Start from on-disk persona and selectively pull only the behavioural
                    # fields from the latest builtin definition. This refreshes prompts and
                    # tool toggles for older installs without clobbering legitimately user-
                    # customised settings like the provider/model choice.
                    merged = dict(existing)
                    for field in self._BUILTIN_REFRESH_FIELDS:
                        if field in persona:
                            merged[field] = persona[field]
                    if not existing.get("knowledge_sources"):
                        merged["knowledge_sources"] = persona.get("knowledge_sources", [])
                    merged["updated_at"] = _now_iso()
                else:
                    merged = {**persona, **existing}
                    if not existing.get("knowledge_sources"):
                        merged["knowledge_sources"] = persona.get("knowledge_sources", [])
                if persona["id"] == "de-criticus" and str(existing.get("name") or "").strip().lower() == "de criticus":
                    merged["name"] = persona["name"]
                if persona["id"] not in self._ALWAYS_REFRESH_BUILTIN_IDS:
                    merged["tools"] = {**persona.get("tools", {}), **existing.get("tools", {})}
                    merged["model_settings"] = {**persona.get("model_settings", {}), **existing.get("model_settings", {})}
                by_id[persona["id"]] = merged
        return sorted(by_id.values(), key=lambda item: str(item.get("id") or ""))

    def _save(self, data: dict[str, Any]) -> None:
        if _contains_secret_like(data):
            raise ValueError("Persona store write blocked because content appears to contain a secret.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


MeetingLLMCall = Callable[..., dict[str, Any]]


class MeetingRunner:
    """Runs a transcript-only persona meeting without granting tool access."""

    def __init__(self, llm_call: MeetingLLMCall | None = None, llm_timeout_seconds: float | None = None):
        self.llm_call = llm_call
        # Defaults to 25s so a local Ollama or a cloud call can actually return
        # a substantive paragraph; the previous 2s default made every meeting
        # turn time out and fall back to deterministic templates. The env var
        # WINTRIP_OUROBOROS_CHAT_MEETING_TURN_TIMEOUT still overrides this for
        # test suites and quick CI runs.
        self.llm_timeout_seconds = max(
            0.01,
            float(
                llm_timeout_seconds
                if llm_timeout_seconds is not None
                else os.getenv("WINTRIP_OUROBOROS_CHAT_MEETING_TURN_TIMEOUT", "25")
            ),
        )

    def run(
        self,
        *,
        topic: str,
        personas: list[dict[str, Any]],
        provider: str,
        model: str,
        meeting_id: str,
        meeting_type: str = "team",
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        meeting_type = _normalize_meeting_type(meeting_type)
        topic_intent = _classify_topic_intent(topic)
        personas = self._ordered_personas(personas)
        participants = [self._public_persona(persona) for persona in personas]
        chair = self._chair_persona(personas)
        transcript: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        def emit(event: dict[str, Any]) -> None:
            events.append(event)
            if event_sink is not None:
                try:
                    event_sink(event)
                except Exception:
                    pass

        if chair:
            agenda = self._chair_led_agenda(chair, personas, meeting_type, topic)
            for index, (round_number, phase, persona, instruction) in enumerate(agenda):
                event = self._run_turn(
                    topic=topic,
                    meeting_type=meeting_type,
                    personas=personas,
                    participants=participants,
                    persona=persona,
                    provider=provider,
                    model=model,
                    meeting_id=meeting_id,
                    round_number=round_number,
                    phase=phase,
                    instruction=instruction,
                    transcript=transcript,
                    max_words=95 if self._is_chair_persona(persona) else 80,
                )
                parrot_handled = False
                candidate = {
                    "round": round_number,
                    "phase": phase,
                    "participant": event["participant"],
                    "content": event["content"],
                }
                # In the development_team flow the five fixed roles are *supposed* to
                # converge on the same files, symbols and tests — that overlap is not
                # parroting, it is collaboration. The anti-parrot circuit was tuned for
                # brainstorms where every speaker should add a new angle, and it produces
                # off-topic "Anders punt:" templates here. Skip it for dev-team meetings.
                disable_anti_parrot = meeting_type == "development_team"
                forced_by_parrot = (
                    not disable_anti_parrot
                    and not self._is_chair_persona(persona)
                    and not event.get("prompt_context", {}).get("used_fallback")
                    and event.get("prompt_context", {}).get("distinctness_reason") == "parroting"
                )
                still_parroting = (
                    not disable_anti_parrot
                    and not self._is_chair_persona(persona)
                    and not event.get("prompt_context", {}).get("used_fallback")
                    and self._looks_like_parroting([*transcript, candidate], event["content"])
                )
                if forced_by_parrot or still_parroting:
                    parrot_handled = True
                    if not any(
                        item.get("phase") == "intervention"
                        and item.get("prompt_context", {}).get("intervention_reason") == "anti_parroting"
                        for item in events
                    ):
                        intervention = self._chair_intervention_event(
                            chair=chair,
                            repeated_persona=persona,
                            meeting_id=meeting_id,
                            meeting_type=meeting_type,
                            round_number=round_number,
                            transcript_turns=len(transcript),
                        )
                        emit(intervention)
                        transcript.append(
                            {
                                "round": round_number,
                                "phase": "intervention",
                                "participant": intervention["participant"],
                                "content": intervention["content"],
                            }
                        )
                    event["phase"] = "anti-parrot-redo"
                    event["prompt_context"]["intervention_reason"] = "anti_parroting_redo"
                    event["prompt_context"]["required_distinct_turn"] = True
                    event["prompt_context"]["forced_distinct_fallback"] = True
                    if still_parroting:
                        event["content"] = self._distinctive_fallback_turn(
                            persona,
                            topic,
                            "anti-parrot-redo",
                            transcript,
                            meeting_type=meeting_type,
                            strict=True,
                        )
                    if not str(event["content"]).strip().lower().startswith("anders punt"):
                        event["content"] = _clip_text(f"Anders punt: {event['content']}", 1800)
                    retry_candidate = {
                        "round": round_number,
                        "phase": "anti-parrot-redo",
                        "participant": event["participant"],
                        "content": event["content"],
                    }
                    if self._looks_like_parroting([*transcript, retry_candidate], event["content"]):
                        event["content"] = self._distinctive_fallback_turn(
                            persona,
                            topic,
                            "anti-parrot-redo",
                            transcript,
                            meeting_type=meeting_type,
                            strict=True,
                        )
                        event["prompt_context"]["forced_distinct_fallback"] = True
                    emit(event)
                    transcript.append(
                        {
                            "round": round_number,
                            "phase": "anti-parrot-redo",
                            "participant": event["participant"],
                            "content": event["content"],
                        }
                    )
                else:
                    emit(event)
                    transcript.append(candidate)
                if not self._is_chair_persona(persona):
                    next_item = agenda[index + 1] if index + 1 < len(agenda) else None
                    if next_item:
                        next_round, _next_phase, next_persona, _next_instruction = next_item
                        floor_control = self._chair_floor_control_event(
                            chair=chair,
                            previous_persona=persona,
                            next_persona=next_persona,
                            meeting_id=meeting_id,
                            meeting_type=meeting_type,
                            topic=topic,
                            next_phase=_next_phase,
                            round_number=next_round if parrot_handled else round_number,
                            transcript_turns=len(transcript),
                            transcript=transcript,
                        )
                        emit(floor_control)
                        transcript.append(
                            {
                                "round": floor_control["round"],
                                "phase": floor_control["phase"],
                                "participant": floor_control["participant"],
                                "content": floor_control["content"],
                            }
                        )
        else:
            if meeting_type == "sprint_planning":
                open_agenda = (
                    (
                        1,
                        "plan-slice",
                        "Lever één sprint-plak: taak, acceptatiecriterium, testcommando, risico en rollback. Maximaal 70 woorden.",
                    ),
                    (
                        2,
                        "plan-check",
                        "Controleer het plan: voeg één ontbrekende afhankelijkheid, stopregel of smoke-run toe. Maximaal 60 woorden.",
                    ),
                )
            elif meeting_type == "brainstorm":
                open_agenda = (
                    (
                        1,
                        "research",
                        "Deep search: noem één bronlaag, waarneming en onzekerheid uit beschikbare read-only context. Maximaal 85 woorden.",
                    ),
                    (
                        2,
                        "research-layer",
                        "Deep think: geef één aanname, alternatief, tegenvoorbeeld of experiment dat de oplossing verdiept. Maximaal 80 woorden.",
                    ),
                )
            else:
                open_agenda = (
                    (
                        1,
                        "input",
                        "Geef je eerste besluitvormende bijdrage: maximaal 80 woorden, één standpunt, één risico en één vervolgstap.",
                    ),
                    (
                        2,
                        "reply",
                        "Reageer op de vorige spreker: maximaal 80 woorden, kies accepteren, aanpassen of parkeren, en eindig besluitbaar.",
                    ),
                )
            for round_number, phase, instruction in open_agenda:
                for persona in personas:
                    event = self._run_turn(
                        topic=topic,
                        meeting_type=meeting_type,
                        personas=personas,
                        participants=participants,
                        persona=persona,
                        provider=provider,
                        model=model,
                        meeting_id=meeting_id,
                        round_number=round_number,
                        phase=phase,
                        instruction=instruction,
                        transcript=transcript,
                        max_words=80,
                    )
                    emit(event)
                    transcript.append(
                        {
                            "round": round_number,
                            "phase": phase,
                            "participant": event["participant"],
                            "content": event["content"],
                        }
                    )

        summary = self._summarize(topic=topic, transcript=transcript, model=model, provider=provider, meeting_type=meeting_type)
        summary_content = self._compact_conversation_text(summary["content"], max_words=180)
        summary_event = {
            "type": "meeting_summary",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "meeting_type": meeting_type,
            "topic_intent": topic_intent,
            "content": _clip_text(summary_content, 3000),
            "summary": _clip_text(summary_content, 3000),
            "provider": provider,
            "model": model,
            "ok": summary["ok"],
            "error": summary["error"],
            "safety_note": (
                "No Cline execution, shell commands, browser control, agent execution, or write tools were run."
            ),
            "next_action": (
                f"Use exact {APPROVAL_PHRASE} only in the existing gated action routes "
                "when real-world changes are intended."
            ),
        }
        emit(summary_event)
        return {
            "meeting_type": meeting_type,
            "topic_intent": topic_intent,
            "participants": participants,
            "rounds": [event for event in events if event.get("type") == "participant_turn"],
            "summary": summary_event["summary"],
            "events": events,
        }

    def _ordered_personas(self, personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [persona for _, persona in sorted(enumerate(personas), key=lambda item: (0 if self._is_chair_persona(item[1]) else 1, item[0]))]

    def _chair_persona(self, personas: list[dict[str, Any]]) -> dict[str, Any] | None:
        for persona in personas:
            if self._is_chair_persona(persona):
                return persona
        return None

    def _is_chair_persona(self, persona: dict[str, Any]) -> bool:
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or "").strip().lower()
        role = str(persona.get("role") or "").strip().lower()
        return persona_id in {"de-voorzitter", "dev-voorman"} or "voorzitter" in name or "voorman" in name or "facilitator" in role

    def _is_critic_persona(self, persona: dict[str, Any]) -> bool:
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or "").strip().lower()
        role = str(persona.get("role") or "").strip().lower()
        tags = persona.get("tags") if isinstance(persona.get("tags"), list) else []
        tag_text = " ".join(str(tag).lower() for tag in tags)
        return "criticus" in persona_id or "critic" in persona_id or "criticus" in name or "critic" in name or "risk" in role or "critic" in tag_text

    def _is_designer_persona(self, persona: dict[str, Any]) -> bool:
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or "").strip().lower()
        role = str(persona.get("role") or "").strip().lower()
        tags = persona.get("tags") if isinstance(persona.get("tags"), list) else []
        tag_text = " ".join(str(tag).lower() for tag in tags)
        return (
            persona_id in {"de-ontwerper", "dev-ontwerper"}
            or "ontwerper" in name
            or "designer" in name
            or "design contract" in role
            or "designer" in tag_text
        )

    def _meeting_type_contract(self, meeting_type: str) -> str:
        meeting_type = _normalize_meeting_type(meeting_type)
        if meeting_type == "sprint_planning":
            return (
                "SPRINTCONTRACT: doel is een uitvoerbaar bouwplan. Elke bijdrage maakt het werk kleiner: taak, eigenaar, "
                "acceptatiecriterium, testcommando, afhankelijkheid, rollback of stopregel. Geen vrije discussie zonder planwaarde."
            )
        if meeting_type == "brainstorm":
            return (
                "BRAINSTORMCONTRACT: doel is onderzoek en oplossingsruimte vergroten. Elke niet-voorzitter doet deep search "
                "op beschikbare read-only bronnen en daarna deep think: aanname, alternatief, tegenvoorbeeld en experiment. "
                "Kritiek is altijd een uitdaging om dieper naar een oplossing te zoeken, nooit een blokkade."
            )
        if meeting_type == "development_team":
            return (
                "ONTWIKKELTEAM-CONTRACT: doel is één werkbare build_plan aan het eind. Vijf vaste rollen werken samen: "
                "Voorman bewaakt het bouwdoel en handoffs; Ontwerper legt interface/files/testhook vast; "
                "De Developper schetst de code-wijziging met letterlijke file paths en symbolen; "
                "De Tester levert een reproduceerbaar testcommando, verwacht signaal en rollback; "
                "Critikus markeert risico's als Blocker of Warning met een concrete actie. "
                "Elke beurt gebruikt een Gas Town-stijl overdracht: MODE, FROM, TO, SUBJECT, BODY, NEXT. "
                "MODE: nudge is normale directe overdracht, MODE: mail is persistente blocker, MODE: handoff is sessiecontinuiteit. "
                "Blockers van Critikus moeten geadresseerd zijn voor Voorman afsluit."
            )
        return (
            "TEAMCONTRACT: doel is besluitvorming. Elke bijdrage helpt kiezen: standpunt, bewijs, spanning, risico, eigenaar "
            "of besluitbare vervolgstap. De voorzitter bewaakt tempo, verschil tussen punten en expliciete woordgeving."
        )

    def _chair_floor_control_event(
        self,
        *,
        chair: dict[str, Any],
        previous_persona: dict[str, Any],
        next_persona: dict[str, Any],
        meeting_id: str,
        meeting_type: str,
        topic: str,
        next_phase: str,
        round_number: int,
        transcript_turns: int,
        transcript: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        previous_name = str(previous_persona.get("name") or previous_persona.get("id") or "de vorige spreker")
        next_name = str(next_persona.get("name") or next_persona.get("id") or "de volgende spreker")
        topic_intent = _classify_topic_intent(topic)
        focus_options = {
            "team": [
                "de besliskeuze",
                "het doorslaggevende risico",
                "de eigenaar",
                "de open vraag",
                "de besluitbare vervolgstap",
                "de stopconditie",
            ],
            "sprint_planning": [
                "de eerste bouwtaak",
                "het acceptatiecriterium",
                "het testcommando",
                "de rollbackroute",
                "de afhankelijkheid",
                "de stopregel",
                "de smoke-run",
            ],
            "brainstorm": [
                "een nieuwe bronlaag waar we nog niet naar gekeken hebben",
                "een aanname die hier nog onzeker is",
                "een alternatief oplossingspad",
                "het ontbrekende tegenvoorbeeld",
                "de oplossingsroute na de kritiek van net",
                "een klein toetsbaar experiment",
            ],
        }
        options = focus_options.get(meeting_type, focus_options["team"])
        assignment_track_key = ""
        opdracht_floor_template: str | None = None
        if meeting_type == "brainstorm" and topic_intent == "opdracht":
            track = self._assignment_track_for_persona_identity(topic, next_persona)
            assignment_track_key = track["key"]
            if next_phase == "research":
                opdracht_options = [
                    "hoe jij dit vanuit jouw rol zou aanpakken",
                    "wat hier vanuit jouw werk als eerste opvalt",
                    "welke eerste praktische stap jij hier zou maken",
                    "waar de opdracht volgens jou het kleinst gemaakt kan worden",
                ]
            elif next_phase == "research-layer":
                opdracht_options = [
                    "welke aanname jij hier nog onzeker vindt",
                    "welk risico jij verder zou willen uitwerken",
                    "wat je hier nog dieper zou willen onderzoeken",
                ]
            elif next_phase == "solution-dive":
                opdracht_options = [
                    "hoe je dit klein en toetsbaar maakt",
                    "welke kleine eerste patch dit voorstel concreet maakt",
                    "welke ene test bewijst dat je voorstel werkt",
                ]
            else:
                opdracht_options = [
                    "hoe we deze ideeën in een werkbare volgorde zetten",
                    "welke stap als eerste op tafel moet komen",
                ]
            opdracht_floor_template = opdracht_options[transcript_turns % len(opdracht_options)]
        existing_text = self._transcript_text(transcript or []).lower()
        ordered = options[transcript_turns % len(options):] + options[: transcript_turns % len(options)]
        focus = next((option for option in ordered if option.lower() not in existing_text), ordered[0])
        if self._is_chair_persona(next_persona):
            content = f"Dank {previous_name}. Ik neem het woord even terug om de lijn op orde te brengen en een besluitbare vervolgstap te maken."
        elif opdracht_floor_template is not None:
            content = f"Dank {previous_name}. {next_name}, {opdracht_floor_template}?"
        else:
            content = f"Dank {previous_name}. Ik geef nu het woord aan {next_name} voor {focus}."
        return {
            "type": "participant_turn",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "round": round_number,
            "phase": "floor-control",
            "meeting_type": meeting_type,
            "participant": self._public_persona(chair),
            "provider": "deterministic",
            "model": "chair-floor-control",
            "content": _clip_text(content, 1800),
            "ok": True,
            "error": "",
            "prompt_context": {
                "social_awareness": True,
                "chair_led": True,
                "meeting_type": meeting_type,
                "floor_control": True,
                "previous_speaker": previous_persona.get("id"),
                "next_speaker": next_persona.get("id"),
                "anti_parrot_required": True,
                "transcript_turns_supplied": transcript_turns,
                "max_words_requested": 35,
                "assignment_track_key": assignment_track_key,
            },
        }

    def _chair_intervention_event(
        self,
        *,
        chair: dict[str, Any],
        repeated_persona: dict[str, Any],
        meeting_id: str,
        meeting_type: str,
        round_number: int,
        transcript_turns: int,
    ) -> dict[str, Any]:
        repeated_name = str(repeated_persona.get("name") or repeated_persona.get("id") or "de spreker")
        redirects = [
            f"Ik stop de echo hier. {repeated_name}, maak er nu een ander bewijsstuk van.",
            f"Ik grijp in op overlap. {repeated_name}, geef nu een eigen risico, test of randvoorwaarde.",
            f"Dit is te dicht op wat al gezegd is. {repeated_name}, draai naar een nieuwe laag.",
        ]
        content = redirects[transcript_turns % len(redirects)]
        return {
            "type": "participant_turn",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "round": round_number,
            "phase": "intervention",
            "meeting_type": meeting_type,
            "participant": self._public_persona(chair),
            "provider": "deterministic",
            "model": "chair-anti-parrot",
            "content": _clip_text(content, 1800),
            "ok": True,
            "error": "",
            "prompt_context": {
                "social_awareness": True,
                "chair_led": True,
                "meeting_type": meeting_type,
                "intervention_reason": "anti_parroting",
                "anti_parrot_required": True,
                "repeated_speaker": repeated_persona.get("id"),
                "transcript_turns_supplied": transcript_turns,
                "max_words_requested": 35,
            },
        }

    def _chair_led_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
        meeting_type: str,
        topic: str,
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        meeting_type = _normalize_meeting_type(meeting_type)
        if meeting_type == "sprint_planning":
            return self._sprint_planning_agenda(chair, personas)
        if meeting_type == "brainstorm":
            return self._brainstorm_agenda(chair, personas, topic)
        if meeting_type == "development_team":
            return self._development_team_agenda(chair, personas, topic)
        return self._team_agenda(chair, personas)

    def _is_developer_persona(self, persona: dict[str, Any]) -> bool:
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or "").strip().lower()
        role = str(persona.get("role") or "").strip().lower()
        tags = persona.get("tags") if isinstance(persona.get("tags"), list) else []
        tag_text = " ".join(str(tag).lower() for tag in tags)
        return (
            persona_id in {"de-developer", "de-developper"}
            or "developper" in name
            or "developer" in name
            or "ouroboros development engineer" in role
            or "developer" in tag_text
        )

    def _is_tester_persona(self, persona: dict[str, Any]) -> bool:
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or "").strip().lower()
        role = str(persona.get("role") or "").strip().lower()
        tags = persona.get("tags") if isinstance(persona.get("tags"), list) else []
        tag_text = " ".join(str(tag).lower() for tag in tags)
        return (
            persona_id == "de-tester"
            or "tester" in name
            or "verification gate" in role
            or "tester" in tag_text
        )

    def _development_team_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
        topic: str,
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        contributors = [persona for persona in personas if persona is not chair]
        designer = next((p for p in contributors if self._is_designer_persona(p)), None)
        developer = next((p for p in contributors if self._is_developer_persona(p)), None)
        tester = next((p for p in contributors if self._is_tester_persona(p)), None)
        critic = next((p for p in contributors if self._is_critic_persona(p)), None)
        exclude_ids = {str(p.get("id") or "") for p in (designer, developer, tester, critic) if p}
        others = [p for p in contributors if str(p.get("id") or "") not in exclude_ids]
        agenda: list[tuple[int, str, dict[str, Any], str]] = []
        topic_hint = _clip_text(topic, 220)
        mail_rule = "Gebruik zichtbaar Gas Town mailformaat: FROM, TO, SUBJECT, BODY, NEXT."

        agenda.append(
            (
                1,
                "opening",
                chair,
                (
                    f"Open als Voorman van het gescheiden OUROBOROS DEVELOPMENT TEAM over '{topic_hint}'. "
                    "Beschrijf in één zin het concrete bouwdoel (wat is na deze build anders). "
                    f"Geef daarna gericht het woord aan {(designer or {}).get('name') or 'Ontwerper'} "
                    "voor het ontwerpcontract (interface, files, testhook). "
                    f"{mail_rule} Maximaal 70 woorden."
                ),
            )
        )

        if designer is not None:
            agenda.append(
                (
                    1,
                    "design-contract",
                    designer,
                    (
                        "Maak het ontwerpcontract voor deze build. Verplicht: benoem de waarneembare uitkomst, verwachte files/componenten, "
                        "interface of input/output, en de testhook die De Tester kan bewijzen. Eindig met een directe TO aan De Developper. "
                        f"{mail_rule} Maximaal 90 woorden."
                    ),
                )
            )

        if developer is not None:
            agenda.append(
                (
                    1,
                    "implementation-route",
                    developer,
                    (
                        "Vertaal bouwdoel plus ontwerpcontract naar een concrete code-wijziging. Verplicht: noem MINSTENS één letterlijk file path "
                        "(bv. `src/cli.py`) en MINSTENS één symbol/function naam (bv. `play_round()`). Schets de implementatie in 1-2 "
                        "zinnen — geen volledige diff. Benoem afhankelijkheden en side-effects. Eindig met de ene vraag die je "
                        "beantwoord wil zien voordat de wijziging veilig is. Als je de bestaande codebase niet kent: noem dán toch "
                        "een PROPOSED file path en zeg dat je `read_file` of `file_search` eerst wil draaien. "
                        f"{mail_rule} Maximaal 105 woorden."
                    ),
                )
            )

        if tester is not None:
            agenda.append(
                (
                    1,
                    "test-plan",
                    tester,
                    (
                        "Maak het voorstel van De Developper bewijsbaar. Noem het exacte testcommando, het verwachte signaal "
                        "(welke assertion / output / statuscode), het faalsignaal (welke foutmelding) en de rollback (welke commit/file/flag). "
                        "Als de wijziging moeilijk te testen is, vraag De Developper om de kleinste hook. "
                        f"{mail_rule} Maximaal 85 woorden."
                    ),
                )
            )

        if critic is not None:
            agenda.append(
                (
                    1,
                    "critic-review",
                    critic,
                    (
                        "Wijs het grootste risico in het huidige voorstel aan, één concrete edge case die het team niet heeft "
                        "geadresseerd, en geef De Developper of De Tester een specifieke actie. Markeer expliciet als Blocker of Warning. "
                        "Bij security-vermoeden: escaleer direct. "
                        f"{mail_rule} Maximaal 80 woorden."
                    ),
                )
            )

        # Optional extra contributors get a single inbreng-turn before round 2 so they still get a voice.
        for extra in others:
            agenda.append(
                (
                    1,
                    "extra-input",
                    extra,
                    (
                        "Lever vanuit jouw rol één concreet inhoudelijk punt over het voorstel tot nu toe — een aanvulling, "
                        "een ontwerpkeuze, of een waarschuwing. Gebruik FROM, TO, SUBJECT, BODY, NEXT. Maximaal 60 woorden."
                    ),
                )
            )

        if developer is not None:
            agenda.append(
                (
                    2,
                    "dev-revise",
                    developer,
                    (
                        "Reageer op de Blockers en Warnings van De Criticus en op de testeisen van De Tester. Pas de implementatie aan: "
                        "welke files/symbols veranderen nu, welke afhankelijkheid is toegevoegd, welk risico is afgedekt. "
                        f"{mail_rule} Maximaal 85 woorden."
                    ),
                )
            )

        if tester is not None:
            agenda.append(
                (
                    2,
                    "test-confirm",
                    tester,
                    (
                        "Bevestig of het herziene voorstel met je testcommando bewijsbaar is. Pas het testcommando aan als de wijzigingen "
                        "dat eisen. Markeer expliciet: groen voor merge, of welke vraag eerst nog open is. "
                        f"{mail_rule} Maximaal 65 woorden."
                    ),
                )
            )

        if critic is not None:
            agenda.append(
                (
                    2,
                    "critic-final",
                    critic,
                    (
                        "Geef je eindoordeel: zijn alle Blockers geadresseerd? Welke Warnings horen expliciet in de bouwprompt "
                        "(en welke kunnen dicht)? Stilte is geen goedkeuring — zeg expliciet 'akkoord' of 'nog niet, want ...'. "
                        f"{mail_rule} Maximaal 60 woorden."
                    ),
                )
            )

        agenda.append(
            (
                2,
                "closing",
                chair,
                (
                    "Sluit nu af als Voorman met EXACT vijf zinnen, in deze volgorde — geen labels, "
                    "geen opsommingstekens, geen tussenkopjes, geen losse vraag aan andere deelnemers:\n"
                    "Zin 1 — Begin met 'Na deze build' en beschrijf in één zin het doel: wat is anders.\n"
                    "Zin 2 — Noem de 1-3 concrete files of symbolen die moeten veranderen, met letterlijke paden of namen.\n"
                    "Zin 3 — Geef het exacte testcommando dat het werk bewijst en het verwachte signaal (statuscode, log-regel of assertion).\n"
                    "Zin 4 — Beschrijf hoe terug te rollen als de test faalt (welke commit, file of feature-flag).\n"
                    "Zin 5 — Lever een formeel build_plan of bouwprompt aan OUROBOROS DEVELOPMENT TEAM build-loop en zeg dat bouwen pas mag na 'Akkoord'.\n"
                    "Onbeantwoorde Criticus-Blockers gaan NIET door — benoem die als zesde zin die start met 'Open blocker:'. "
                    "Geen interne regiewoorden ('spoor', 'deep think', 'acceptatie blijft', 'approvalpoort', 'bouwticket'). "
                    "Maximaal 140 woorden. Geen vragen, geen vragen aan deelnemers — dit is de afsluiting."
                ),
            )
        )
        return agenda

    def _team_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        contributors = [persona for persona in personas if persona is not chair]
        first_name = contributors[0].get("name") if contributors else "de tafel"
        agenda: list[tuple[int, str, dict[str, Any], str]] = [
            (
                1,
                "opening",
                chair,
                (
                    "Open als voorzitter een besluitvormende teamvergadering. Noem het besluit dat nodig is, "
                    "de volgorde standpunt-risico-keuze en geef daarna expliciet het woord aan "
                    f"{first_name}. Maximaal 65 woorden."
                ),
            )
        ]
        for persona in contributors:
            agenda.append(
                (
                    1,
                    "input",
                    persona,
                    (
                        "Geef één besluitvormende bijdrage. Kies een standpunt, bewijsstuk of risico dat de keuze scherper maakt. "
                        "Benoem wat vandaag wel of niet besloten kan worden. Spreek natuurlijk, maximaal 75 woorden."
                    ),
                )
            )
        if contributors:
            agenda.append(
                (
                    1,
                    "chair-bridge",
                    chair,
                    (
                        "Vat als voorzitter de keuze samen. Benoem optie A/B, de belangrijkste spanning en één vraag die nodig is "
                        "om tot besluit of eigenaar te komen. Maximaal 70 woorden."
                    ),
                )
            )
            for persona in contributors:
                agenda.append(
                    (
                        2,
                        "reply",
                        persona,
                        (
                            "Reageer op de beslisvraag van de voorzitter. Kies: accepteren, aanpassen of parkeren. "
                            "Eindig met één besluitbaar punt, eigenaar of stopconditie. Maximaal 70 woorden."
                        ),
                    )
                )
        agenda.append(
            (
                2,
                "closing",
                chair,
                (
                    "Sluit als voorzitter af in maximaal 90 woorden. Geef gewone spreektaal met vier korte regels: "
                    "Besluit, Open vraag, Eigenaar, Volgende stap. Wijs geen acties toe buiten de approval-flow."
                ),
            )
        )
        return agenda

    def _sprint_planning_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        contributors = [persona for persona in personas if persona is not chair]
        first_name = contributors[0].get("name") if contributors else "de tafel"
        agenda: list[tuple[int, str, dict[str, Any], str]] = [
            (
                1,
                "opening",
                chair,
                (
                    "Open als voorzitter een sprint planning. Zet direct timebox, sprintdoel, bouwvolgorde en testpoort neer. "
                    f"Geef daarna het woord aan {first_name}. Maximaal 55 woorden."
                ),
            )
        ]
        for persona in contributors:
            agenda.append(
                (
                    1,
                    "plan-slice",
                    persona,
                    (
                        "Lever één sprint-plak: backlog-item, eerste taak, acceptatiecriterium, testcommando en grootste risico. "
                        "Maak het uitvoerbaar voor een ontwikkelagent. Maximaal 70 woorden."
                    ),
                )
            )
        if contributors:
            agenda.append(
                (
                    1,
                    "plan-bridge",
                    chair,
                    (
                        "Maak als voorzitter een concept-sprintbord. Benoem volgorde, eigenaar, acceptatietest, rollback "
                        "en de ene vraag die nog nodig is om te starten. Maximaal 80 woorden."
                    ),
                )
            )
            for persona in contributors:
                agenda.append(
                    (
                        2,
                        "plan-check",
                        persona,
                        (
                            "Controleer het concept-plan als delivery-check. Voeg één ontbrekend acceptatiecriterium, testcommando, "
                            "afhankelijkheid, rollback of stopregel toe. Maximaal 60 woorden."
                        ),
                    )
                )
        agenda.append(
            (
                2,
                "closing",
                chair,
                (
                    "Presenteer het sprintplan als voorzitter in natuurlijke spreektaal. Benoem sprintdoel, taken, acceptatie, "
                    "test en rollback, en wanneer een agent pas mag bouwen. Geen labels of opsommingsheaders; spreek het uit zoals aan een echte tafel. "
                    "Geen externe uitvoering buiten de approval-flow."
                ),
            )
        )
        return agenda

    def _brainstorm_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
        topic: str,
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        contributors = [persona for persona in personas if persona is not chair]
        first_name = contributors[0].get("name") if contributors else "de tafel"
        critic = next((persona for persona in contributors if self._is_critic_persona(persona)), None)
        solution_contributors = [persona for persona in contributors if persona is not critic]
        topic_intent = _classify_topic_intent(topic)
        if topic_intent == "opdracht":
            opening_instruction = (
                "Open als voorzitter een opdracht-brainstorm. Vraag om concrete oplossingssporen: component, ontwerpkeuze, "
                "acceptatiebewijs en risico. Geen algemene lagenlijst. "
                f"Geef daarna het woord aan {first_name}. Maximaal 65 woorden."
            )
        elif topic_intent == "storing":
            opening_instruction = (
                "Open als voorzitter een diagnose-brainstorm. Vraag om foutsignaal, vermoedelijke laag, herstelpad en preventie. "
                f"Geef daarna het woord aan {first_name}. Maximaal 65 woorden."
            )
        elif topic_intent == "idee":
            opening_instruction = (
                "Open als voorzitter een idee-brainstorm. Vraag om waarde, variant, prototype en leerexperiment. "
                f"Geef daarna het woord aan {first_name}. Maximaal 65 woorden."
            )
        else:
            opening_instruction = (
                "Open als voorzitter een brainstormsessie. Zet het contract neer: eerst deep search per persona, daarna deep think "
                "op aannames, alternatieven, risico's en experimenten. "
                f"Geef daarna het woord aan {first_name}. Maximaal 65 woorden."
            )
        agenda: list[tuple[int, str, dict[str, Any], str]] = [
            (
                1,
                "opening",
                chair,
                opening_instruction,
            )
        ]
        for persona in contributors:
            if topic_intent == "opdracht":
                track = self._assignment_track_for_persona_identity(topic, persona)
                if self._is_critic_persona(persona):
                    instruction = (
                        f"Jouw vaste oplossingsspoor is {track['title']}. Toets dit spoor hard: welk component bouwen we, welk bewijs ontbreekt, "
                        "welk risico maakt dit spoor onveilig of te groot? Maximaal 85 woorden."
                    )
                else:
                    instruction = (
                        f"Jouw vaste oplossingsspoor is {track['title']}. Noem component, ontwerpkeuze, eerste acceptatiebewijs en waarom dit "
                        "de opdracht kleiner maakt. Geen abstracte bronlaag. Maximaal 85 woorden."
                    )
            elif self._is_critic_persona(persona):
                instruction = (
                    "Deep search: gebruik de beschikbare read-only kennis- of Brave-context als die aanwezig is. Noem één bronlaag, "
                    "één concreet ontbrekend bewijs en één kritisch risico als uitdaging voor een sterkere oplossing. Maximaal 85 woorden."
                )
            else:
                instruction = (
                    "Deep search: gebruik de beschikbare read-only kennis- of Brave-context als die aanwezig is. Noem één bronlaag, "
                    "één concrete waarneming en één onzekerheid die verder denken verdient. Maximaal 85 woorden."
                )
            agenda.append(
                (
                    1,
                    "research",
                    persona,
                    instruction,
                )
            )
        if contributors:
            agenda.append(
                (
                    1,
                    "research-bridge",
                    chair,
                    (
                        "Cluster als voorzitter de concrete oplossingssporen. Kies maximaal drie kansrijke sporen en benoem "
                        "welk bewijs per spoor nodig is. Geef daarna gericht het woord voor deep think. Maximaal 80 woorden."
                        if topic_intent == "opdracht"
                        else (
                            "Cluster als voorzitter de deep-search lagen. Benoem welke bronlaag ontbreekt en geef de volgende spreker "
                            "gericht het woord voor deep think, niet voor besluitvorming. Maximaal 80 woorden."
                        )
                    ),
                )
            )
            for persona in contributors:
                if topic_intent == "opdracht":
                    track = self._assignment_track_for_persona_identity(topic, persona)
                    if self._is_critic_persona(persona):
                        instruction = (
                            f"Deep think op hetzelfde spoor {track['title']}: welke aanname kan breken, welke contracttest bewijst het, "
                            "en welke grens houdt de patch klein? Maximaal 80 woorden."
                        )
                    else:
                        instruction = (
                            f"Deep think op hetzelfde spoor {track['title']}: geef de ontwerp-trade-off, één edge case en één testbare eerste patch. "
                            "Maximaal 80 woorden."
                        )
                elif self._is_critic_persona(persona):
                    instruction = (
                        "Deep think: verdiep je risico als productieve uitdaging. Formuleer de aanname die kan breken, "
                        "een tegenvoorbeeld en de vraag die de oplossing beter maakt. Je blokkeert niet. Maximaal 80 woorden."
                    )
                else:
                    instruction = (
                        "Deep think: vertrek vanuit je eigen bronlaag. Geef één aanname, alternatief, tegenvoorbeeld of experiment "
                        "dat de oplossingsruimte vergroot. Maximaal 80 woorden."
                    )
                agenda.append(
                    (
                        2,
                        "research-layer",
                        persona,
                        instruction,
                    )
                )
            if critic and solution_contributors:
                critic_name = str(critic.get("name") or "de criticus")
                for persona in solution_contributors[:3]:
                    track = self._assignment_track_for_persona_identity(topic, persona)
                    agenda.append(
                        (
                            2,
                            "solution-dive",
                            persona,
                            (
                                (
                                    f"Behandel de opmerking van {critic_name} als uitdaging voor {track['title']}. Maak dit spoor patchbaar: "
                                    "welke file/route, welke test, welke rollbackgrens? Maximaal 85 woorden."
                                )
                                if topic_intent == "opdracht"
                                else (
                                    f"Behandel de opmerking van {critic_name} als uitdaging, niet als block. Doe een oplossing-dive: "
                                    "welke aanpassing, randvoorwaarde, test of alternatief maakt het voorstel sterker? Maximaal 85 woorden."
                                )
                            ),
                        )
                    )
            agenda.append(
                (
                    2,
                    "research-synthesis",
                    chair,
                    (
                        "Maak als voorzitter een opdrachtsynthese: gekozen oplossingsspoor, eerste patch, acceptatietest, risico "
                        "en approval-gated volgende stap. Maximaal 90 woorden."
                        if topic_intent == "opdracht"
                        else (
                            "Maak als voorzitter een synthese van deep search en deep think. Benoem bronlagen, kansrijke oplossing, "
                            "kritieke onzekerheid en volgend experiment. Maximaal 90 woorden."
                        )
                    ),
                )
            )
        agenda.append(
            (
                2,
                "closing",
                chair,
                (
                    "Sluit als voorzitter af in natuurlijke spreektaal. Vertel kort welk voorstel we als eerste bouwen, welke eerste patch en acceptatietest erbij horen, "
                    "en wanneer een agent pas mag beginnen. Geen labels of opsommingsheaders; geen vakjargon als 'spoor' of 'approvalpoort'. Geen uitvoering buiten de approval-flow."
                    if topic_intent == "opdracht"
                    else (
                        "Sluit de brainstorm af in natuurlijke spreektaal. Vertel kort wat het sterkste inzicht is, welke richting het meest belooft, "
                        "wat nog onzeker blijft en welke onderzoeksstap nu volgt. Geen labels of opsommingsheaders, en geen uitvoering buiten de approval-flow."
                    )
                ),
            )
        )
        return agenda

    def _run_turn(
        self,
        *,
        topic: str,
        meeting_type: str,
        personas: list[dict[str, Any]],
        participants: list[dict[str, Any]],
        persona: dict[str, Any],
        provider: str,
        model: str,
        meeting_id: str,
        round_number: int,
        phase: str,
        instruction: str,
        transcript: list[dict[str, Any]],
        max_words: int,
    ) -> dict[str, Any]:
        participant = self._public_persona(persona)
        topic_intent = _classify_topic_intent(topic)
        assignment_track_key = ""
        if (
            meeting_type == "brainstorm"
            and topic_intent == "opdracht"
            and not self._is_chair_persona(persona)
        ):
            try:
                assignment_track_key = self._assignment_track_for_persona_identity(topic, persona).get("key", "")
            except Exception:
                assignment_track_key = ""
        model_settings = persona.get("model_settings") if isinstance(persona.get("model_settings"), dict) else {}
        turn_provider = str(model_settings.get("provider") or provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        turn_model = str(model_settings.get("name") or persona.get("model") or model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        fallback_model = str(model_settings.get("fallback_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        fallback_provider = str(model_settings.get("fallback_provider") or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        # Small local models (codellama, gemma, ouroboros:latest, llama:3b, phi3) lose track of
        # long system + user prompts and drift after 2-3 sentences. Detect them and swap in
        # compact variants so the conversation stays on-topic and the deterministic compositor
        # can finish the structural work.
        is_light = _is_light_model(turn_provider, turn_model) or _is_light_model(fallback_provider, fallback_model)
        if is_light:
            system_prompt = self._light_system_prompt(persona, meeting_type, topic)
            user_prompt = self._light_turn_prompt(
                topic=topic,
                meeting_type=meeting_type,
                phase=phase,
                instruction=instruction,
                transcript=transcript,
                persona=persona,
            )
            max_words = min(max_words, 70)
        else:
            system_prompt = self._social_system_prompt(persona, personas, topic, meeting_type=meeting_type)
            user_prompt = self._turn_prompt(
                topic=topic,
                meeting_type=meeting_type,
                round_number=round_number,
                phase=phase,
                instruction=instruction,
                transcript=transcript,
                persona=persona,
            )
        fallback = self._fallback_turn(persona, topic, phase, transcript, meeting_type=meeting_type)
        response = self._call_model(
            prompt=user_prompt,
            system_prompt=system_prompt,
            provider=turn_provider,
            model=turn_model,
            fallback=fallback,
            fallback_provider=fallback_provider,
            fallback_model=fallback_model,
        )
        used_fallback = str(response.get("content") or "").strip() == str(fallback or "").strip()
        content = self._compact_conversation_text(response["content"], max_words=max_words)
        content = _clip_text(content, 1800)
        forced_distinct = False
        distinctness_reason = ""
        generic_content = self._generic_meeting_content(content)
        candidate = {
            "round": round_number,
            "phase": phase,
            "participant": participant,
            "content": content,
        }
        # Same rationale as in `run`: development_team turns are role-aligned by design
        # so the anti-parrot replacement (which falls back to generic templates) hurts
        # more than it helps.
        anti_parrot_active = meeting_type != "development_team"
        parroting = (
            anti_parrot_active
            and not self._is_chair_persona(persona)
            and self._looks_like_parroting([*transcript, candidate], content)
        )
        if anti_parrot_active and not self._is_chair_persona(persona) and (parroting or generic_content):
            forced_distinct = True
            distinctness_reason = "parroting" if parroting else "generic_fallback"
            content = self._distinctive_fallback_turn(
                persona,
                topic,
                phase,
                transcript,
                meeting_type=meeting_type,
                strict=parroting or phase == "anti-parrot-redo",
            )
        content = _strip_meeting_meta_language(content, persona_name=participant.get("name") or "")
        return {
            "type": "participant_turn",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "round": round_number,
            "phase": phase,
            "meeting_type": meeting_type,
            "participant": participant,
            "provider": turn_provider,
            "model": turn_model,
            "content": _clip_text(content, 1800),
            "ok": response["ok"],
            "error": response["error"],
            "prompt_context": {
                "social_awareness": True,
                "chair_led": any(self._is_chair_persona(item) for item in personas),
                "meeting_type": meeting_type,
                "topic_intent": topic_intent,
                "topic_intent_label": _topic_intent_label(topic_intent),
                "meeting_contract": self._meeting_type_contract(meeting_type),
                "topic_intent_contract": _topic_intent_contract(topic_intent),
                "deep_search_required": bool(meeting_type == "brainstorm" and not self._is_chair_persona(persona)),
                "deep_think_required": bool(meeting_type == "brainstorm" and not self._is_chair_persona(persona)),
                "sprint_planning_required": bool(meeting_type == "sprint_planning"),
                "decision_meeting_required": bool(meeting_type == "team"),
                "anti_parrot_required": True,
                "critic_is_challenge": bool(meeting_type == "brainstorm" and self._is_critic_persona(persona)),
                "other_participants": [
                    {"id": item.get("id"), "name": item.get("name"), "role": item.get("role")}
                    for item in participants
                    if item.get("id") != participant.get("id")
                ],
                "transcript_turns_supplied": len(transcript),
                "max_words_requested": max_words,
                "forced_distinct_fallback": forced_distinct,
                "distinctness_reason": distinctness_reason,
                "used_fallback": used_fallback,
                "assignment_track_key": assignment_track_key,
                "light_model_path": is_light,
            },
        }

    def _light_system_prompt(self, persona: dict[str, Any], meeting_type: str, topic: str) -> str:
        """Compact system prompt for small local models (≤ 7B).

        These models lose track of the verbose AgenK-style persona prompts; instead we hand
        them a short directive tied to their role and the meeting type. The deterministic
        compositor downstream (`_extract_build_prompt`) will pick up structure that the
        model misses.
        """
        meeting_type = _normalize_meeting_type(meeting_type)
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or persona.get("id") or "deelnemer")
        role = str(persona.get("role") or "")
        if meeting_type == "development_team":
            role_brief = {
                "de-voorzitter": (
                    "Je leidt het ontwikkelteam als Voorman. Open in één zin met het bouwdoel (start met 'Na deze build'). "
                    "Geef expliciet het woord aan Ontwerper, De Developper, De Tester of Critikus. "
                    "Sluit af met vijf korte zinnen: doel, files/symbolen, exact testcommando, rollback, formeel build_plan na Akkoord."
                ),
                "dev-voorman": (
                    "Je bent Voorman. Maak het werk klein, wijs de volgende rol aan, en bewaak dat er een formeel build_plan uitkomt. "
                    "Gebruik Gas Town mailstijl: FROM, TO, SUBJECT, BODY, NEXT."
                ),
                "dev-ontwerper": (
                    "Je bent Ontwerper. Leg CONTRACT, FILES, INTERFACE en TEST_HOOK vast voor De Developper en De Tester. "
                    "Gebruik Gas Town mailstijl: FROM, TO, SUBJECT, BODY, NEXT."
                ),
                "de-developer": (
                    "Je bent De Developper. Noem letterlijke file paths (met /) en symbol-namen die veranderen. "
                    "Schets de wijziging in 1-2 zinnen, dan één gerichte vraag aan De Tester of De Criticus."
                ),
                "de-developper": (
                    "Je bent De Developper. Noem letterlijke file paths (met /) en symbol-namen die veranderen. "
                    "Schets de wijziging in 1-2 zinnen, dan één gerichte vraag aan De Tester of De Criticus."
                ),
                "dev-developper": (
                    "Je bent De Developper. Noem letterlijke file paths (met /) en symbol-namen die veranderen. "
                    "Schets de wijziging in 1-2 zinnen en draag expliciet over aan De Tester. Gebruik FROM, TO, SUBJECT, BODY, NEXT."
                ),
                "de-tester": (
                    "Je bent De Tester. Geef het exacte testcommando (pytest/npm test/curl/cargo), het verwachte signaal "
                    "(statuscode of assertion), het faalsignaal en de rollback (welke commit/file/flag te reverten). "
                    "Geen 'handmatig in de UI klikken'."
                ),
                "dev-tester": (
                    "Je bent De Tester. Geef het exacte testcommando, verwacht signaal, faalsignaal en rollback. "
                    "Gebruik FROM, TO, SUBJECT, BODY, NEXT en draag terug aan Voorman/Critikus."
                ),
                "de-criticus": (
                    "Je bent Critikus. Wijs één Blocker of Warning aan met concrete actie voor De Developper of De Tester. "
                    "Bij security-vermoeden: escaleer en gebruik het woord Blocker. Stilte is geen goedkeuring."
                ),
                "dev-critikus": (
                    "Je bent Critikus. Wijs één Blocker of Warning aan met concrete actie voor De Developper of De Tester. "
                    "Gebruik FROM, TO, SUBJECT, BODY, NEXT. Stilte is geen goedkeuring."
                ),
            }.get(persona_id, f"Je bent {name} ({role}). Geef één concrete inhoudelijke bijdrage met een file, symbol, test of risico.")
        elif meeting_type == "brainstorm":
            role_brief = f"Je bent {name} ({role}). Geef één concreet inzicht over '{_clip_text(topic, 100)}': een waarneming, aanname, alternatief of klein testbaar experiment."
        elif meeting_type == "sprint_planning":
            role_brief = f"Je bent {name} ({role}). Geef één bouwbare slice voor '{_clip_text(topic, 100)}': taak, acceptatiecriterium, testcommando, rollback."
        else:
            role_brief = f"Je bent {name} ({role}). Geef één besluitvormende bijdrage over '{_clip_text(topic, 100)}': standpunt, bewijs of besluitbare vervolgstap."

        return (
            f"{role_brief}\n"
            "Schrijf in natuurlijke spreektaal, 2 tot 4 zinnen. Begin niet met je eigen naam. "
            "Geen labels of opsommingstekens. Geen interne regiewoorden ('spoor', 'deep think', 'acceptatie blijft', 'approvalpoort', 'bouwticket'). "
            "Verwijs minstens één keer met naam naar de vorige spreker, tenzij je de eerste bent."
        )

    def _light_turn_prompt(
        self,
        *,
        topic: str,
        meeting_type: str,
        phase: str,
        instruction: str,
        transcript: list[dict[str, Any]],
        persona: dict[str, Any] | None = None,
    ) -> str:
        """Compact user-prompt for small local models — drops the verbose contracts."""
        last = self._last_substantive_turn(transcript)
        if last:
            last_line = (
                f"Vorige spreker {last['name']} ({last.get('phase') or 'beurt'}): \"{_clip_text(last['content'], 320)}\"\n"
                "Reageer hier inhoudelijk op."
            )
        else:
            last_line = "Je bent de eerste inhoudelijke spreker. Open met een concrete stelling over het onderwerp."
        clean_instruction = _clip_text(str(instruction or "").splitlines()[0] if instruction else "", 320)
        return (
            f"Onderwerp: {_clip_text(topic, 240)}\n"
            f"Fase: {phase}\n"
            f"{last_line}\n\n"
            f"Opdracht: {clean_instruction}\n\n"
            "Antwoord in 2-4 zinnen, concreet en op het onderwerp. Noem een file, symbol, testcommando of risico waar relevant."
        )

    def _social_system_prompt(self, persona: dict[str, Any], personas: list[dict[str, Any]], topic: str, *, meeting_type: str = "team") -> str:
        topic_intent = _classify_topic_intent(topic)
        meeting_type = _normalize_meeting_type(meeting_type)
        others = [
            f"- {item.get('name') or item.get('id')}: {item.get('role') or 'geen rol opgegeven'}"
            for item in personas
            if item.get("id") != persona.get("id")
        ]
        rules = persona.get("rules") if isinstance(persona.get("rules"), list) else []
        base_prompt = str(persona.get("system_prompt") or persona.get("instructions") or "").strip()
        return "\n".join(
            part
            for part in [
                base_prompt,
                (
                    "Je bent in het gescheiden OUROBOROS DEVELOPMENT TEAM, niet in OUROBOROS MEETING."
                    if meeting_type == "development_team"
                    else "Je bent in een Ouroboros Vergadering."
                ),
                f"Onderwerp: {_clip_text(topic, 1200)}",
                f"Onderwerpsoort: {_topic_intent_label(topic_intent)}",
                _topic_intent_contract(topic_intent),
                "Andere aanwezigen:\n" + ("\n".join(others) if others else "- Geen andere persona's."),
                f"Jouw Rol: {persona.get('role') or 'Niet opgegeven'}",
                f"Jouw Regels: {', '.join(str(rule) for rule in rules) if rules else 'Geen extra regels opgegeven.'}",
                f"Jouw Toon: {persona.get('tone') or 'Grounded, practical, inspectable'}",
                f"Jouw Taal: {persona.get('language') or 'nl'}",
                self._knowledge_context(persona),
                (
                    "Instructie: Schrijf alsof je hardop aan tafel spreekt, niet als rapport. "
                    "Houd het kort: 3 tot 5 zinnen, maximaal één kort lijstje als dat echt helpt. "
                    "Help lichtere modellen door expliciet te kiezen voor één punt tegelijk. "
                    "Letterlijke herhaling is bij voorbaat niet toegestaan: als je het eens bent, voeg een nieuwe invalshoek, beperking of test toe. "
                    "Verwar een opdracht, storing, idee en vraag niet met elkaar; laat je bijdrage passen bij de onderwerpsoort. "
                    "Als je voorzitter bent, leid jij de volgorde en grijp je in wanneer twee deelnemers elkaar herhalen. "
                    "In brainstorms is kritiek altijd een uitdaging om dieper naar een oplossing te zoeken, nooit een blokkade. "
                    "Voer geen tools uit en claim geen externe acties."
                ),
            ]
            if part
        )

    def _turn_prompt(
        self,
        *,
        topic: str,
        meeting_type: str,
        round_number: int,
        phase: str,
        instruction: str,
        transcript: list[dict[str, Any]],
        persona: dict[str, Any] | None = None,
    ) -> str:
        topic_intent = _classify_topic_intent(topic)
        transcript_text = self._transcript_text(transcript)
        last_substantive = self._last_substantive_turn(transcript)
        if last_substantive:
            last_block = (
                f"Laatste inhoudelijke spreker: {last_substantive['name']}.\n"
                f"Wat zij/hij net zei: \"{_clip_text(last_substantive['content'], 600)}\"\n"
                "Reageer hier inhoudelijk op: bevestigen met nieuwe onderbouwing, aanvullen "
                "met een concrete observatie, of gemotiveerd weerleggen met een tegenvoorbeeld."
            )
        else:
            persona_name = str((persona or {}).get("name") or "")
            last_block = (
                "Je bent de eerste inhoudelijke spreker. Open met een concrete stelling die "
                "direct over het onderwerp gaat — geen procedurewoorden, geen samenvatting "
                f"van wat de voorzitter zei{(', ' + persona_name + ' kan meteen positie nemen') if persona_name else ''}."
            )
        substantive_instruction = (
            "Schrijf je beurt zoals iemand aan een echte tafel praat. Eén concreet inhoudelijk punt over "
            f"'{_clip_text(topic, 200)}', niet over de vergadering zelf. Geef minstens één van: een "
            "harde claim met onderbouwing, een verifieerbaar voorbeeld, een aanname die kan breken, een "
            "concrete vervolgstap of een ene gerichte vraag aan een andere deelnemer. Verwijs minstens "
            "één keer met naam naar wat een eerdere spreker zei, tenzij je de eerste bent. "
            "Geen markdown-koppen, geen lijstjes langer dan drie items, maximaal 80 woorden. "
            "Geen interne regiewoorden ('spoor', 'deep think', 'acceptatie blijft', 'approvalpoort', "
            "'bouwticket'). Begin niet met je eigen naam."
        )
        return "\n\n".join(
            [
                f"Onderwerp: {_clip_text(topic, 1600)}",
                f"Vergadertype: {MEETING_TYPE_LABELS.get(meeting_type, 'Team vergadering')}",
                f"Onderwerpsoort: {_topic_intent_label(topic_intent)}",
                self._meeting_type_contract(meeting_type),
                _topic_intent_contract(topic_intent),
                f"Ronde {round_number} ({phase})",
                instruction,
                last_block,
                "Volledige transcriptie tot nu toe:",
                transcript_text or "Nog geen eerdere bijdragen.",
                substantive_instruction,
            ]
        )

    def _last_substantive_turn(self, transcript: list[dict[str, Any]]) -> dict[str, Any] | None:
        for item in reversed(transcript):
            phase = str(item.get("phase") or "")
            if phase in {"floor-control", "intervention", "opening"}:
                continue
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            return {
                "name": str(participant.get("name") or participant.get("id") or "een eerdere spreker"),
                "role": str(participant.get("role") or ""),
                "content": content,
                "phase": phase,
            }
        return None

    def _distinctive_retry_instruction(self, repeated_content: str, transcript: list[dict[str, Any]]) -> str:
        repeated_terms = self._meaningful_terms(repeated_content)[:10]
        previous_terms = self._meaningful_terms(self._transcript_text(transcript))[:24]
        avoid_terms = ", ".join(_dedupe_strings([*repeated_terms, *previous_terms])[:12])
        avoid_clause = f" Vermijd deze kernwoorden als kapstok: {avoid_terms}." if avoid_terms else ""
        return (
            "De voorzitter heeft net ingegrepen omdat je bijdrage te veel overlapte met een andere spreker. "
            "Je moet nu iets anders zeggen: geef één nieuw bewijsstuk, ander risico, randvoorwaarde, test of tegenvoorbeeld. "
            "Begin met 'Anders punt:' en herhaal de vorige conclusie niet."
            f"{avoid_clause} Maximaal 65 woorden."
        )

    def _summarize(
        self,
        *,
        topic: str,
        transcript: list[dict[str, Any]],
        model: str,
        provider: str = DEFAULT_PROVIDER,
        meeting_type: str = "team",
    ) -> dict[str, Any]:
        meeting_type = _normalize_meeting_type(meeting_type)
        topic_intent = _classify_topic_intent(topic)
        summary_instructions = {
            "team": "Sluit af als besluitnotulen. Noem: besluit, open keuze, eigenaar en eerstvolgende approval-gated stap.",
            "sprint_planning": "Sluit af als sprintkaart in natuurlijke spreektaal. Vertel kort sprintdoel, taken, acceptatiecriteria, test en rollback, en wanneer een agent pas mag beginnen. Geen labels of opsommingsheaders.",
            "brainstorm": "Sluit af als onderzoekssynthese. Noem: bronlagen, beste oplossingsrichting, onzekerheden en volgend experiment.",
        }
        if meeting_type == "brainstorm" and topic_intent == "opdracht":
            summary_instructions["brainstorm"] = (
                "Sluit af als opdrachtsynthese voor ontwikkelwerk. Kies één bouwvolgorde en noem: eerste patch, acceptatiebewijs, "
                "privacy/veiligheidsgrens en wat pas na Akkoord gebouwd of uitgevoerd mag worden. Knip geen losse zinnen uit het transcript."
            )
        elif meeting_type == "brainstorm" and topic_intent == "storing":
            summary_instructions["brainstorm"] = (
                "Sluit af als diagnosesynthese. Noem: vermoedelijke laag, foutsignaal, herstelpad, bewijs en structurele preventie."
            )
        elif meeting_type == "brainstorm" and topic_intent == "idee":
            summary_instructions["brainstorm"] = (
                "Sluit af als idee-synthese. Noem: waarde, varianten, spannendste aanname, prototype en leerexperiment."
            )
        prompt = "\n\n".join(
            [
                f"Onderwerp: {_clip_text(topic, 1600)}",
                f"Vergadertype: {MEETING_TYPE_LABELS.get(meeting_type, 'Team vergadering')}",
                f"Onderwerpsoort: {_topic_intent_label(topic_intent)}",
                "Volledige vergaderingstranscriptie:",
                self._transcript_text(transcript) or "Geen bijdragen.",
                summary_instructions.get(meeting_type, summary_instructions["team"]),
            ]
        )
        fallback = self._fallback_summary(topic, transcript, meeting_type=meeting_type)
        return self._call_model(
            prompt=prompt,
            system_prompt=(
                "Je bent de neutrale synthese-laag van een Ouroboros Vergadering. "
                "Vat alleen kort samen in heldere spreektaal; voer geen tools, shell, browser of agents uit."
            ),
            provider=provider,
            model=model,
            fallback=fallback,
        )

    def _compact_conversation_text(self, text: str, max_words: int = 90) -> str:
        cleaned_lines = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                if cleaned_lines and cleaned_lines[-1]:
                    cleaned_lines.append("")
                continue
            line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            line = re.sub(r"^\s*[-*]\s+", "- ", line)
            cleaned_lines.append(line)
        cleaned = "\n".join(cleaned_lines).strip()
        words = cleaned.split()
        if len(words) <= max_words:
            return cleaned
        clipped = " ".join(words[:max_words]).rstrip(" ,;:")
        return clipped + "..."

    def _looks_like_parroting(self, transcript: list[dict[str, Any]], current_content: str) -> bool:
        current_terms = self._meaningful_terms(current_content)
        if len(current_terms) < 5:
            return False
        current_set = set(current_terms)
        for previous in reversed(transcript[:-1]):
            participant = previous.get("participant") if isinstance(previous.get("participant"), dict) else {}
            if self._is_public_chair(participant):
                continue
            previous_terms = self._meaningful_terms(str(previous.get("content") or ""))
            if len(previous_terms) < 5:
                continue
            previous_set = set(previous_terms)
            overlap = len(current_set & previous_set)
            if overlap < 4:
                continue
            containment = overlap / max(1, min(len(current_set), len(previous_set)))
            jaccard = overlap / max(1, len(current_set | previous_set))
            if containment >= 0.5 or jaccard >= 0.32:
                return True
            if self._shared_bigram_count(previous_terms, current_terms) >= 2:
                return True
        return False

    def _generic_meeting_content(self, text: str) -> bool:
        cleaned = str(text or "").strip().lower()
        if not cleaned:
            return True
        generic_markers = [
            "ik sluit aan vanuit",
            "praktisch en toetsbaar",
            "één keuze vastleggen",
            "een keuze vastleggen",
            "één risico expliciet maken",
            "een risico expliciet maken",
            "anders punt: ik voeg geen echo toe",
            "één nieuw criterium, één grens en één stopmoment",
            "een nieuw criterium, een grens en een stopmoment",
            "de richting lijkt bruikbaar",
            "scope te verkleinen",
            "zonder tool-uitvoering af te spreken",
        ]
        return any(marker in cleaned for marker in generic_markers)

    def _meaningful_terms(self, text: str) -> list[str]:
        stopwords = {
            "aan",
            "als",
            "bij",
            "dat",
            "de",
            "die",
            "dit",
            "een",
            "en",
            "er",
            "het",
            "hier",
            "ik",
            "in",
            "is",
            "met",
            "niet",
            "nog",
            "om",
            "op",
            "te",
            "tot",
            "van",
            "vanuit",
            "voor",
            "we",
            "wel",
            "zou",
            "mijn",
            "jouw",
            "geen",
            "punt",
            "anders",
            "moet",
            "naar",
            "ook",
            "the",
            "and",
            "for",
            "that",
            "this",
            "with",
            "deep",
            "search",
            "think",
            "bronlaag",
            "waarneming",
            "onzekerheid",
            "aanname",
            "alternatief",
            "tegenvoorbeeld",
            "experiment",
            "sprint",
            "taak",
            "acceptatie",
            "bewijs",
            "zichtbaar",
            "eerste",
            "klaar",
            "betekent",
            "patch",
            "voorstel",
            "groene",
            "smoke-run",
            "uitvoering",
        }
        words = re.findall(r"[A-Za-zÀ-ÿ0-9_:-]{4,}", str(text or "").lower())
        return [word for word in words if word not in stopwords]

    def _shared_bigram_count(self, left: list[str], right: list[str]) -> int:
        left_bigrams = set(zip(left, left[1:]))
        right_bigrams = set(zip(right, right[1:]))
        return len(left_bigrams & right_bigrams)

    def _is_public_chair(self, participant: dict[str, Any]) -> bool:
        return self._is_chair_persona(
            {
                "id": participant.get("id"),
                "name": participant.get("name"),
                "role": participant.get("role"),
            }
        )

    def _call_model(
        self,
        *,
        prompt: str,
        system_prompt: str,
        provider: str,
        model: str,
        fallback: str,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> dict[str, Any]:
        """Call the configured LLM once, and once more on a local fallback before giving up.

        The first attempt uses the persona's preferred provider/model. If that returns
        an error or empty content (e.g. cloud API key missing, network down, timeout),
        a second attempt is made against `fallback_provider`/`fallback_model` — usually
        the local Ollama default — so meetings still get LLM-generated content even when
        the persona's primary route is unavailable. Only when both attempts fail do we
        fall back to the deterministic transcript text.
        """
        if self.llm_call is None:
            return {"ok": True, "content": fallback, "error": ""}

        first = self._invoke_llm_once(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
        )
        if first["ok"] and first["content"].strip():
            return {**first, "fallback_used": False}

        fallback_provider = (fallback_provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        fallback_model = (fallback_model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        same_route = fallback_provider == str(provider or "").strip().lower() and fallback_model == str(model or "").strip()
        if not same_route:
            second = self._invoke_llm_once(
                prompt=prompt,
                system_prompt=system_prompt,
                provider=fallback_provider,
                model=fallback_model,
            )
            if second["ok"] and second["content"].strip():
                return {
                    **second,
                    "fallback_used": True,
                    "primary_error": first.get("error") or "",
                    "primary_provider": provider,
                    "primary_model": model,
                }

        # Both attempts failed — use deterministic transcript text.
        error = str(first.get("error") or "").strip() or "Meeting model returned no content."
        return {"ok": False, "content": fallback, "error": error, "fallback_used": False}

    def _invoke_llm_once(
        self,
        *,
        prompt: str,
        system_prompt: str,
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            try:
                future = executor.submit(
                    self.llm_call,
                    prompt=prompt,
                    provider=provider,
                    model=model,
                    system_prompt=system_prompt,
                    history=[],
                    images=[],
                )
                result = future.result(timeout=self.llm_timeout_seconds)
            except TypeError:
                future = executor.submit(self.llm_call, prompt=prompt, model=model, system_prompt=system_prompt, history=[])
                result = future.result(timeout=self.llm_timeout_seconds)
        except concurrent.futures.TimeoutError:
            return {
                "ok": False,
                "content": "",
                "error": f"Meeting model call timed out after {self.llm_timeout_seconds:.1f}s.",
            }
        except Exception as exc:
            return {"ok": False, "content": "", "error": str(exc)}
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

        if isinstance(result, dict):
            content = str(result.get("content") or result.get("response") or "").strip()
            return {
                "ok": bool(result.get("ok", True)) and bool(content),
                "content": content,
                "error": str(result.get("error") or ""),
            }
        content = str(result or "").strip()
        return {"ok": bool(content), "content": content, "error": ""}

    def _fallback_turn(
        self,
        persona: dict[str, Any],
        topic: str,
        phase: str,
        transcript: list[dict[str, Any]],
        *,
        meeting_type: str = "team",
    ) -> str:
        meeting_type = _normalize_meeting_type(meeting_type)
        topic_intent = _classify_topic_intent(topic)
        if self._is_chair_persona(persona):
            if phase == "opening":
                if meeting_type == "sprint_planning":
                    return (
                        f"Ik open de sprint planning over '{_clip_text(topic, 180)}'. We maken dit bouwbaar: eerst taken, "
                        "dan acceptatie en test, daarna rollback en approvalpoort. Ik geef nu het woord aan de eerste deelnemer."
                    )
                if meeting_type == "brainstorm":
                    if topic_intent == "opdracht":
                        return (
                            f"Ik open de brainstorm over de opdracht '{_clip_text(topic, 180)}'. Eerst zoeken we implementatieroutes, "
                            "daarna denken we door op ontwerpkeuzes, risico's en acceptatiebewijs. Ik geef nu het woord aan de eerste deelnemer."
                        )
                    if topic_intent == "storing":
                        return (
                            f"Ik open de diagnose-brainstorm over '{_clip_text(topic, 180)}'. Eerst isoleren we foutsignalen en lagen, "
                            "daarna bepalen we herstelpad en structurele preventie. Ik geef nu het woord aan de eerste deelnemer."
                        )
                    if topic_intent == "idee":
                        return (
                            f"Ik open de idee-brainstorm over '{_clip_text(topic, 180)}'. Eerst zoeken we waarde en varianten, "
                            "daarna toetsen we aannames met een klein prototype. Ik geef nu het woord aan de eerste deelnemer."
                        )
                    return (
                        f"Ik open de brainstorm over '{_clip_text(topic, 180)}'. Eerst verkennen we bronlagen, "
                        "daarna toetsen we aannames, alternatieven en experimenten. Ik geef nu het woord aan de eerste deelnemer."
                    )
                return (
                    f"Ik open de teamvergadering over '{_clip_text(topic, 180)}'. We werken naar een keuze toe: standpunt, "
                    "spanning, eigenaar en besluitbare vervolgstap. Ik geef nu het woord aan de eerste deelnemer."
                )
            if phase == "chair-bridge":
                return (
                    "Ik orden de keuze: welke optie nemen we nu, welke vraag blijft open en wie bewaakt de eerste toets? "
                    "Ik geef de tweede ronde langs besluit, eigenaar en stopconditie."
                )
            if phase == "intervention":
                return (
                    "Ik stop de echo hier. De volgende bijdrage moet een ander bewijsstuk, risico of test toevoegen."
                )
            if phase == "plan-bridge":
                return (
                    "Ik zet het sprintbord neer: taak, eigenaar, acceptatie, testcommando en rollback. "
                    "De volgende spreker vult alleen het ontbrekende delivery-risico aan."
                )
            if phase in {"research-bridge", "research-synthesis"}:
                if topic_intent == "opdracht":
                    if phase == "research-synthesis":
                        return (
                            "Mijn samenvatting: de eerste bouwstap is read-only meten, niet herstellen. "
                            "Eerst een health-rollup endpoint en metadata-only telemetry, daarna pas een compact statuspaneel. "
                            f"Herstelknoppen, rollback en agentbouw beginnen pas zodra iemand expliciet {APPROVAL_PHRASE} geeft."
                        )
                    return (
                        "Mijn bouwvolgorde: eerst meten met watchdog en telemetry, dan een compact statuspaneel, "
                        "en pas daarna herstelknoppen met rollback. "
                        "De volgende spreker gaat dieper in op zijn eigen laag binnen die volgorde."
                    )
                if topic_intent == "storing":
                    return (
                        "Ik leg de diagnoselagen naast elkaar: foutsignaal, oorzaak, herstelpad en preventie. "
                        "De volgende spreker gaat dieper in op de laag die nog het minst bewezen is."
                    )
                if topic_intent == "idee":
                    return (
                        "Ik leg de ideelagen naast elkaar: waarde, variant, randvoorwaarde en prototype. "
                        "De volgende spreker gaat dieper in op de meest leerzame aanname."
                    )
                return (
                    "Ik leg de bronlagen naast elkaar: waarneming, aanname, alternatief en experiment. "
                    "De volgende spreker neemt de laag die nog het meest onzeker is."
                )
            if phase == "closing":
                if meeting_type == "development_team":
                    topic_hint = _clip_text(topic, 160)
                    return (
                        f"Doel: lever een werkbare wijziging voor '{topic_hint}' die meteen door een uitvoerende agent gerund kan worden. "
                        "Wijzigingen: de tafel benoemde de file/symbol-route hierboven — pak de kleinste eenheid eerst. "
                        "Acceptatie: het testcommando van De Tester moet groen draaien vanaf een schone state met het verwachte signaal. "
                        "Rollback: revert van de laatste commit of de feature-flag terug op uit. "
                        f"Uitvoerende agent: /codex (of /claude / /roo) na expliciet {APPROVAL_PHRASE}."
                    )
                if meeting_type == "sprint_planning":
                    return (
                        "Sprintdoel: maak de eerstvolgende verbetering klein en testbaar. "
                        "Taken: patch, regressietest en smoke-run. "
                        "Test en rollback: groen voor merge, anders terug naar voorstel. "
                        f"Een agent begint pas met bouwen zodra iemand expliciet {APPROVAL_PHRASE} geeft."
                    )
                if meeting_type == "brainstorm":
                    if topic_intent == "opdracht":
                        return (
                            "Mijn voorstel: begin met een read-only stabiliteitsmonitor die niets herstart. "
                            "Eerste patch: `/api/ouroboros/health-rollup` met metadata-only JSONL-statusregels. "
                            "Als twee opeenvolgende checks missen, kleurt alleen die laag rood, met timestamp en foutcode. "
                            f"Herstel, rollback en agentbouw beginnen pas zodra iemand expliciet {APPROVAL_PHRASE} geeft."
                        )
                    if topic_intent == "storing":
                        return (
                            "Sterkste inzicht: diagnose gaat voor verbetering. "
                            "Beste richting: bewijs eerst de falende laag. "
                            "Nog onzeker: welk foutsignaal doorslaggevend is. "
                            "Volgende stap: één herstelcheck lokaal en inspecteerbaar maken."
                        )
                    if topic_intent == "idee":
                        return (
                            "Sterkste inzicht: het idee moet eerst waarde en randvoorwaarden krijgen. "
                            "Beste richting: klein prototype met één meetbare leeruitkomst. "
                            "Nog onzeker: welke gebruiker of workflow het meest baat heeft. "
                            "Volgende stap: één prototype-experiment formuleren."
                        )
                    return (
                        "Sterkste inzicht: de oplossing moet uit bronlagen en experimenten komen. "
                        "Beste richting: test eerst de meest onzekere aanname. "
                        "Nog onzeker: welke bron is doorslaggevend. "
                        "Volgende onderzoeksstap: één experiment formuleren zonder externe uitvoering."
                    )
                return (
                    "Besluit: de volgende stap blijft klein en controleerbaar. "
                    "Open vraag: wie bewaakt de eerste toets en de rollback? "
                    "Volgende stap: pas na Akkoord gaat een gekozen agent bouwen of extern uitvoeren."
                )
        return self._distinctive_fallback_turn(persona, topic, phase, transcript, meeting_type=meeting_type)

    def _assignment_solution_tracks(self, topic: str) -> list[dict[str, str]]:
        text = str(topic or "").lower()
        if _contains_phrase(text, ("stabiel", "monitor", "gemonitord", "monitoring", "health", "watchdog")):
            return [
                {
                    "key": "watchdog",
                    "title": "watchdog-service",
                    "research": "een lokale scheduler pingt backend, Tauri bridge, modelpoort en opslag elke minuut en zet elke laag op groen, geel of rood",
                    "proof": "na twee gemiste checks verschijnt rood met laatste foutregel en timestamp",
                    "risk": "als de watchdog zelf te veel mag doen, wordt monitoring stiekem uitvoering",
                    "think": "maak de watchdog read-only: hij schrijft status en advies, maar herstarten blijft via de approval-route",
                    "solution": "start met een `/api/ouroboros/health-rollup` contracttest en een JSONL-regel per check",
                },
                {
                    "key": "telemetry",
                    "title": "telemetry-JSONL",
                    "research": "elke meeting en modelcall bewaart provider, latency, timeout, retry-teller, GPU/CPU-druk en laatste fout als inspecteerbare JSONL",
                    "proof": "een testmeeting levert minimaal één regel met status, duur, provider en foutveld",
                    "risk": "ruwe logs kunnen ruis of privé-inhoud opslaan",
                    "think": "log alleen metagegevens en korte foutcodes; transcriptinhoud blijft buiten de health-telemetry",
                    "solution": "voeg een kleine telemetry-writer toe met schema-test en redactie op geheimen",
                },
                {
                    "key": "recovery",
                    "title": "herstelcontroller",
                    "research": "de cockpit toont per laag een veilige herstelknop met wachtrijstatus, laatste logregel en duidelijke rollbackgrens",
                    "proof": "een droge run toont queued, running, waiting-for-Akkoord, done of failed zonder shellactie",
                    "risk": "gebruikers kunnen herstel verwarren met automatisch bouwen",
                    "think": "scheid diagnose, advies en actie visueel; alleen de actieknop vraagt exact Akkoord",
                    "solution": "bouw eerst een dry-run endpoint dat herstelstappen plant maar niets uitvoert",
                },
                {
                    "key": "status-ui",
                    "title": "statuspaneel",
                    "research": "het eerste scherm toont backend, Tauri, modelpoort, opslag en GPU als vaste statusrijen met laatste meting",
                    "proof": "bij backend offline blijft persona-lijst zichtbaar als cached readback plus duidelijke rode backendstatus",
                    "risk": "te veel tekst maakt de cockpit weer onrustig",
                    "think": "gebruik compacte statuschips en open details pas op klik; de meetingtekst blijft ondergeschikt aan systeemstatus",
                    "solution": "voeg een statusmodel toe en test dat de UI niet springt als waarden veranderen",
                },
                {
                    "key": "rollback",
                    "title": "rollback-register",
                    "research": "elke werkende binary, backendconfig en modelkeuze krijgt een herkenbare laatste-goede markering",
                    "proof": "na een mislukte smoke-run kan de cockpit de laatste-goede versie tonen zonder te gissen",
                    "risk": "rollback zonder bewijs kan oude fouten terugzetten",
                    "think": "koppel rollback alleen aan een groene smoke-run en bewaar waarom die versie geldig is",
                    "solution": "schrijf `last_good.json` met build-id, config hash en smoke-resultaat",
                },
                {
                    "key": "circuit-breaker",
                    "title": "modelpoort-circuitbreaker",
                    "research": "modelcalls krijgen timeout, korte fallbacktekst en providerstatus zodat een trage call geen Load failed veroorzaakt",
                    "proof": "een kunstmatige timeout levert binnen de limiet transcript-fallback en foutcode op",
                    "risk": "fallback kan inhoudelijk te dun zijn",
                    "think": "laat fallback alleen de beurt redden en markeer hem zichtbaar als fallback in telemetry",
                    "solution": "test één trage modelcall en controleer dat de meeting blijft laden",
                },
            ]
        return [
            {
                "key": "vertical-slice",
                "title": "dunne verticale slice",
                "research": "kies één route van invoer naar zichtbaar resultaat en laat alle extra's buiten scope",
                "proof": "één acceptatietest bewijst de route end-to-end",
                "risk": "de eerste slice kan te klein lijken om waarde te tonen",
                "think": "maak de slice waardevol door een echte gebruikersuitkomst te kiezen",
                "solution": "formuleer één patch, één test en één rollbackgrens",
            },
            {
                "key": "contract-first",
                "title": "contract-first implementatie",
                "research": "leg eerst het API- of data-contract vast voordat UI of agentgedrag wordt aangepast",
                "proof": "schema-test faalt eerst en wordt daarna groen",
                "risk": "een contract zonder workflow voelt abstract",
                "think": "koppel het contract aan één zichtbaar scherm of CLI-uitkomst",
                "solution": "schrijf de contracttest en één minimale adapter",
            },
        ]

    def _select_assignment_track(self, topic: str, transcript: list[dict[str, Any]], seed: int) -> dict[str, str]:
        tracks = self._assignment_solution_tracks(topic)
        existing_text = self._transcript_text(transcript).lower()
        ordered = tracks[seed % len(tracks):] + tracks[: seed % len(tracks)]
        return next(
            (
                track
                for track in ordered
                if track["title"].lower() not in existing_text
            ),
            ordered[0],
        )

    def _assignment_track_for_persona_identity(self, topic: str, persona: dict[str, Any]) -> dict[str, str]:
        tracks = self._assignment_solution_tracks(topic)
        by_key = {track["key"]: track for track in tracks}
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or "").strip().lower()
        role = str(persona.get("role") or "").strip().lower()
        text = " ".join((persona_id, name, role))

        if self._is_critic_persona(persona):
            preferred_keys = ("telemetry", "contract-first")
        elif "ontwerp" in text or "design" in text or "interaction" in text or "product" in text:
            preferred_keys = ("status-ui", "vertical-slice")
        elif "nina" in text or "ai" in text or "model" in text:
            preferred_keys = ("circuit-breaker", "contract-first")
        elif "wintrip" in text or "thinker" in text:
            preferred_keys = ("recovery", "vertical-slice")
        elif "engineer" in text or "backend" in text or "tauri" in text:
            preferred_keys = ("watchdog", "contract-first")
        elif "poocky" in text or "netwerk" in text or "network" in text:
            preferred_keys = ("rollback", "vertical-slice")
        else:
            seed = sum(ord(ch) for ch in text)
            return tracks[seed % len(tracks)]

        for key in preferred_keys:
            if key in by_key:
                return by_key[key]
        seed = sum(ord(ch) for ch in text)
        return tracks[seed % len(tracks)]

    def _assignment_track_for_persona(
        self,
        topic: str,
        transcript: list[dict[str, Any]],
        persona: dict[str, Any],
        seed: int,
    ) -> dict[str, str]:
        tracks = self._assignment_solution_tracks(topic)
        persona_id = str(persona.get("id") or "").strip()
        persona_name = str(persona.get("name") or persona.get("id") or "").strip()
        for item in reversed(transcript):
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            same_persona = bool(
                persona_id
                and str(participant.get("id") or "").strip() == persona_id
                or persona_name
                and str(participant.get("name") or "").strip() == persona_name
            )
            if not same_persona:
                continue
            content = str(item.get("content") or "").lower()
            for track in tracks:
                if track["title"].lower() in content:
                    return track
        return self._assignment_track_for_persona_identity(topic, persona) or self._select_assignment_track(topic, transcript, seed)

    def _distinctive_fallback_turn(
        self,
        persona: dict[str, Any],
        topic: str,
        phase: str,
        transcript: list[dict[str, Any]],
        *,
        meeting_type: str = "team",
        strict: bool = False,
    ) -> str:
        meeting_type = _normalize_meeting_type(meeting_type)
        topic_intent = _classify_topic_intent(topic)
        role = str(persona.get("role") or "").strip()
        name = str(persona.get("name") or persona.get("id") or "deelnemer").strip()
        prefix = "Anders punt: " if phase == "anti-parrot-redo" else ""
        role_clause = f" vanuit {role}" if role else ""
        topic_hint = _clip_text(topic, 90)
        seed = sum(ord(ch) for ch in str(persona.get("id") or persona.get("name") or phase)) + len(transcript)
        existing_text = self._transcript_text(transcript).lower()
        if meeting_type == "sprint_planning" and phase in {"plan-slice", "plan-check", "anti-parrot-redo"}:
            transcript_phases = {str(item.get("phase") or "") for item in transcript}
            effective_phase = "plan-check" if phase == "anti-parrot-redo" and "plan-bridge" in transcript_phases else phase
            if topic_intent == "storing":
                sprint_items = [
                    ("diagnose", "foutsignaal, reproduceerstap en laatste logregel"),
                    ("herstelpad", "veilige restart, statusfeedback en rollback"),
                    ("incidentbewijs", "health-endpoint, latency en retry-teller"),
                    ("gebruikersmelding", "heldere fouttekst en volgende actie"),
                    ("regressietest", "failing test, fix en smoke-run"),
                    ("preventie", "monitoringregel en stopconditie"),
                ]
            elif topic_intent == "idee":
                sprint_items = [
                    ("prototype", "hypothese, kleine demo en feedbackmoment"),
                    ("gebruikerswaarde", "doelgroep, workflow en meetbare opbrengst"),
                    ("variantkeuze", "twee alternatieven en één selectiecriterium"),
                    ("randvoorwaarde", "wat buiten scope valt en waarom"),
                    ("leerexperiment", "verwachte uitkomst, observatie en vervolgkeuze"),
                    ("risicocheck", "wat het idee onbruikbaar zou maken"),
                ]
            else:
                sprint_items = [
                    ("opdrachtomschrijving", "doel, scope en non-goal"),
                    ("implementatiestap", "kleinste patch, geraakt bestand en eigenaar"),
                    ("acceptatiepoort", "acceptatiecriterium, testcommando en smoke-run"),
                    ("monitoringcontract", "statussignaal, meetfrequentie en grenswaarde"),
                    ("rollbackroute", "laatst werkende configuratie en terugvalkeuze"),
                    ("approval-route", f"wachtrijstatus en exacte {APPROVAL_PHRASE}-poort"),
                ]
            ordered_sprint_items = sprint_items[seed % len(sprint_items):] + sprint_items[: seed % len(sprint_items)]
            item, check = next(
                (
                    candidate
                    for candidate in ordered_sprint_items
                    if candidate[0].lower() not in existing_text and candidate[1].split(",", 1)[0].lower() not in existing_text
                ),
                ordered_sprint_items[0],
            )
            if effective_phase == "plan-check":
                return _clip_text(
                    f"{prefix}{name} doet de delivery-check op {item}. Ontbrekende grens: {check}. "
                    "Stop als dat signaal rood blijft of de rollback niet benoemd is.",
                    1800,
                )
            sprint_templates = [
                f"{prefix}{name} zet {item} bovenaan. Klaar betekent zichtbaar bewijs van {check}. "
                "Pas daarna is de patch meer dan een voorstel.",
                f"{prefix}Voor {name} is {item} de dunste bouwstap. Acceptatie: {check}. "
                "Zonder groene smoke-run blijft dit buiten uitvoering.",
                f"{prefix}{name} knipt {item} los als eerste ticket. Meet {check}; "
                "bij falen gaat de kaart terug naar analyse.",
            ]
            return _clip_text(sprint_templates[seed % len(sprint_templates)], 1800)
        if meeting_type == "brainstorm" and phase in {"research", "research-layer", "solution-dive", "anti-parrot-redo"}:
            transcript_phases = {str(item.get("phase") or "") for item in transcript}
            if phase == "anti-parrot-redo":
                effective_phase = "research-layer" if "research-bridge" in transcript_phases else "research"
            else:
                effective_phase = phase
            if topic_intent == "opdracht":
                if effective_phase == "research":
                    track = self._assignment_track_for_persona_identity(topic, persona)
                    research_text = _natural_first_letter(track["research"])
                    proof_text = track["proof"]
                    risk_text = track["risk"]
                    if self._is_critic_persona(persona):
                        return _clip_text(
                            f"{prefix}Mijn zorg bij dit voorstel: {risk_text}. "
                            f"Voordat ik dit akkoord vind, wil ik zien dat {proof_text}.",
                            1800,
                        )
                    return _clip_text(
                        f"{prefix}{research_text}. "
                        f"Het eerste bewijs dat dit werkt: {proof_text}.",
                        1800,
                    )
                track = self._assignment_track_for_persona(topic, transcript, persona, seed)
                think_text = _natural_first_letter(track["think"])
                proof_text = track["proof"]
                risk_text = track["risk"]
                solution_text = track["solution"]
                if effective_phase == "solution-dive":
                    return _clip_text(
                        f"{prefix}Mijn concrete voorstel: {solution_text}. "
                        "Daarna pas verbreden naar de andere lagen.",
                        1800,
                    )
                if self._is_critic_persona(persona):
                    return _clip_text(
                        f"{prefix}De aanname die hier kan breken: {risk_text}. "
                        f"{think_text}.",
                        1800,
                    )
                return _clip_text(
                    f"{prefix}{think_text}. "
                    f"De toets blijft hetzelfde: {proof_text}.",
                    1800,
                )
            if topic_intent == "storing":
                source_layers = [
                    "runtime-log en health endpoint",
                    "Tauri/NVIDIA startspoor",
                    "modelprovider en timeoutmetingen",
                    "meeting transcript en snapshot-opslag",
                    "UI-scrollgedrag en actieve sprekerbalk",
                    "approval-wachtrij en agentrouter",
                    "rollbackconfig en laatste werkende build",
                ]
            elif topic_intent == "idee":
                source_layers = [
                    "gebruikerswaarde en workflow",
                    "mogelijke interactievariant",
                    "prototypevorm en demo-grens",
                    "randvoorwaarde en non-goal",
                    "leerexperiment en feedbacksignaal",
                    "risico bij opschalen",
                    "verrassend tegenvoorbeeld",
                ]
            elif topic_intent == "vraag":
                source_layers = [
                    "definitie en begrenzing",
                    "verschil met verwante begrippen",
                    "concreet voorbeeld",
                    "tegenvoorbeeld",
                    "praktische consequentie",
                    "beslisregel voor toepassing",
                ]
            else:
                source_layers = [
                    "doel en gewenste uitkomst",
                    "architectuurgrens tussen backend, Tauri en modelpoort",
                    "acceptatiecriteria en smoke-test",
                    "monitoringcontract en statuskleuren",
                    "rollbackroute en releasepad",
                    "agent-approval workflow",
                    "observability en auditlog",
                ]
            ordered_layers = source_layers[seed % len(source_layers):] + source_layers[: seed % len(source_layers)]
            layer = next((candidate for candidate in ordered_layers if candidate.lower() not in existing_text), ordered_layers[0])
            if effective_phase == "research":
                if self._is_critic_persona(persona):
                    if topic_intent == "opdracht":
                        critic_templates = [
                            f"{prefix}In {layer} mis ik bewijs: welke acceptatiecheck laat zien dat '{topic_hint}' echt gebouwd is? "
                            "Het risico is dat de opdracht te breed blijft voor één veilige patch.",
                            f"{prefix}Bij {layer} houd ik de implementatie graag uitvoerbaar met één non-goal, "
                            "één acceptatiecriterium en één stopregel.",
                        ]
                        return _clip_text(critic_templates[seed % len(critic_templates)], 1800)
                    if topic_intent == "idee":
                        critic_templates = [
                            f"{prefix}Rond {layer} klinkt het aantrekkelijk, maar het bewijs van waarde ontbreekt nog. "
                            "Wat ik wil zien: één prototype dat snel leert.",
                            f"{prefix}Bij {layer} wil ik weten wanneer dit idee de moeite niet waard is. "
                            "Dat maakt de volgende variant sterker.",
                        ]
                        return _clip_text(critic_templates[seed % len(critic_templates)], 1800)
                    if topic_intent == "vraag":
                        critic_templates = [
                            f"{prefix}Bij {layer} merk ik dat we een andere vraag dreigen te beantwoorden dan gesteld. "
                            "Eerst het onderscheid scherp maken.",
                        ]
                        return _clip_text(critic_templates[seed % len(critic_templates)], 1800)
                    critic_templates = [
                        f"{prefix}Rond {layer} mis ik bewijs: welke concrete fout laat '{topic_hint}' breken? "
                        "Ik zou eerst een meting maken die techniek, wachtrij en modelkeuze van elkaar scheidt.",
                        f"{prefix}In {layer} schuilt het risico dat een mooie oplossing de echte oorzaak maskeert. "
                        "Daarom eerst één falsifieerbare check die de route kan ontkrachten.",
                    ]
                    return _clip_text(critic_templates[seed % len(critic_templates)], 1800)
                if topic_intent == "opdracht":
                    research_templates = [
                        f"{prefix}De opdracht wordt bouwbaar zodra {layer} een eigen acceptatiebewijs krijgt. "
                        "De vraag is welke ontwerpkeuze de eerste patch het kleinst maakt.",
                        f"{prefix}Bij {layer} zie ik dat we een implementatieroute met expliciet acceptatiebewijs nodig hebben. "
                        "De vraag: welk testcommando bewijst dat de opdracht werkt?",
                        f"{prefix}In {layer} zoek ik een voorbeeld dat de bouwrichting verkleint. "
                        "Onzeker blijft welke grens buiten scope moet blijven.",
                    ]
                    return _clip_text(research_templates[seed % len(research_templates)], 1800)
                if topic_intent == "idee":
                    research_templates = [
                        f"{prefix}Het idee krijgt waarde zodra {layer} concreet wordt. "
                        "De vraag: welk prototype leert het snelst?",
                        f"{prefix}Bij {layer} wil ik eerst varianten vergelijken voordat we bouwen. "
                        "De vraag: welk feedbacksignaal beslist tussen die varianten?",
                    ]
                    return _clip_text(research_templates[seed % len(research_templates)], 1800)
                if topic_intent == "vraag":
                    research_templates = [
                        f"{prefix}Bij {layer} vraagt dit eerst om onderscheid en voorbeeld. "
                        "Onzeker: welke vergelijking de gebruiker nodig heeft.",
                    ]
                    return _clip_text(research_templates[seed % len(research_templates)], 1800)
                research_templates = [
                    f"{prefix}{layer.capitalize()} kan los van de rest groen of rood staan. "
                    "Onzeker: welk signaal de eerste breuk voorspelt.",
                    f"{prefix}De oplossing wordt sterker als {layer} eigen telemetrie krijgt. "
                    "Vraag: welke meting maakt een herstelpad zichtbaar?",
                    f"{prefix}In {layer} zoek ik een afwijkend patroon. "
                    "Onzeker blijft of de storing bij runtime, UI of providerkeuze begint.",
                ]
                return _clip_text(research_templates[seed % len(research_templates)], 1800)
            if effective_phase == "solution-dive":
                if topic_intent == "opdracht":
                    return _clip_text(
                        f"{prefix}De kritiek vertaal ik naar een bouwexperiment rond {layer}: "
                        "verwachte uitkomst, acceptatiebewijs en rollbackgrens. Zo blijft de opdracht uitvoerbaar.",
                        1800,
                    )
                if topic_intent == "idee":
                    return _clip_text(
                        f"{prefix}De kritiek vertaal ik naar een prototype rond {layer}: "
                        "welke variant, welk feedbacksignaal en welke stopvraag leren het meest?",
                        1800,
                    )
                return _clip_text(
                    f"{prefix}Ik behandel de kritiek als testontwerp en bouw een klein experiment rond {layer}: "
                    "verwacht signaal, faalsignaal en herstelactie. Als het faalt, scherpt dat de oplossing aan.",
                    1800,
                )
            if topic_intent == "opdracht":
                think_templates = [
                    f"{prefix}Mijn aanname is dat {layer} de opdracht klein genoeg maakt. Een alternatief is eerst een contracttest schrijven. "
                    "Tegenvoorbeeld: de patch werkt, maar monitoring ontbreekt; dan is acceptatie nog niet rond.",
                    f"{prefix}Bij {layer} zou ik eerst de dunste verticale route bouwen en de rest expliciet buiten scope houden. "
                    "Experiment: één test die succes en rollback tegelijk zichtbaar maakt.",
                    f"{prefix}De aanname dat {layer} voldoende richting geeft, kan vallen als de taak te breed blijft. "
                    "Dan moet de opdracht geknipt worden in criterium, patch en bewijs.",
                ]
                return _clip_text(think_templates[seed % len(think_templates)], 1800)
            if topic_intent == "idee":
                think_templates = [
                    f"{prefix}Mijn aanname is dat {layer} waarde oplevert. Een alternatief is een kleiner prototype met één meetbare reactie. "
                    "Tegenvoorbeeld: gebruikers snappen het niet; dan wint de eenvoudigere variant.",
                    f"{prefix}Bij {layer} zou ik twee varianten tonen en meten welke vraag spontaan ontstaat. "
                    "Dat houdt het idee onderzoekend in plaats van voortijdig bouwend.",
                ]
                return _clip_text(think_templates[seed % len(think_templates)], 1800)
            if topic_intent == "vraag":
                think_templates = [
                    f"{prefix}De aanname is dat {layer} het verschil verklaart. Een alternatief is een concreet voorbeeld naast een tegenvoorbeeld. "
                    "Dan wordt duidelijk of dit een uitleg, besluit of opdracht moet worden.",
                ]
                return _clip_text(think_templates[seed % len(think_templates)], 1800)
            think_templates = [
                f"{prefix}Mijn aanname is dat {layer} de bottleneck zichtbaar maakt. Een alternatief: een sandbox-smoke-run "
                "per laag. Tegenvoorbeeld: alles staat op groen maar de meeting faalt; dan moet telemetrie per beurt leidend worden.",
                f"{prefix}Een alternatief: laat de cockpit eerst een mini-diagnose draaien en pas daarna nieuwe tekst genereren. "
                "Experiment: dwing één fout af en kijk of het hersteladvies daadwerkelijk verandert.",
                f"{prefix}De aanname dat {layer} genoeg bewijs geeft, kan vallen als de bron zwijgt. "
                "Dan hoort er een tweede bronlaag naast de eerste.",
            ]
            return _clip_text(think_templates[seed % len(think_templates)], 1800)
        options = [
            (
                "Stabiliteitsmeter",
                "stabiliteitsmeter",
                f"Ik zou de stabiliteit eerst zichtbaar maken{role_clause}. Geef backend, Tauri, modelpoort en opslag elk een groen/geel/rood-status, zodat meteen duidelijk is welke laag hapert.",
            ),
            (
                "Watchdog",
                "watchdog",
                "Mijn aanvullende punt is monitoring zelf. Laat lokaal elke minuut health, latency en laatste fout meten; na twee missers moet de cockpit herstelstatus tonen in plaats van opnieuw vergadertekst te produceren.",
            ),
            (
                "Herstelpad",
                "herstelpad",
                "Ik wil een expliciet herstelpad. Leg vast welke knop of agent backend, frontend en Tauri veilig herstart, met voortgang, laatste logregel en zichtbare bevestiging dat NVIDIA werkelijk actief is.",
            ),
            (
                "Regressieschild",
                "regressieschild",
                "Voor zelfverbetering hoort er een rem op de deur. Elke verbetering krijgt eerst een failing test, daarna de patch en daarna een smoke-run; zonder groene test blijft het een voorstel.",
            ),
            (
                "Telemetrie",
                "telemetrie",
                "Ik mis nog telemetrie per overleg. Bewaar model-timeouts, Load-failed oorzaak, retry-teller en gekozen provider, zodat verbetering uit waarnemingen komt en niet uit indrukken.",
            ),
            (
                "Werkgeheugen",
                "werkgeheugen",
                "Het werkgeheugen moet inspecteerbaar blijven. Schrijf besluiten, open risico's en uitgevoerde checks als JSONL; de app mag leren van zulke regels, niet van verborgen aannames.",
            ),
            (
                "Agentwachtrij",
                "agentwachtrij",
                "Voor het ontwikkelteam wil ik een zichtbare wachtrij. Bouwtaken moeten queued, running, waiting-for-Akkoord, done of failed zijn, zodat starten na akkoord niet verstopt raakt.",
            ),
            (
                "UI-anker",
                "ui-anker",
                "Aan de UI-kant moet het sprekerkader een anker blijven. Geef de balk vaste hoogte en kap de gedachtenloop netjes af, zodat het kader niet wegzakt wanneer iemand langer denkt.",
            ),
            (
                "ApprovalGate",
                "approvalgate",
                f"De grens voor uitvoering moet scherp blijven. Bouwen of externe acties starten alleen na exact {APPROVAL_PHRASE}; alles daarvoor is plan, testvoorstel of lokale analyse.",
            ),
            (
                "Zelfverbeterlus",
                "zelfverbeterlus",
                "De zelfverbetering moet als lus worden behandeld. Feedback wordt issue, acceptatiecriterium, test, patch en auditregel; zo leert de app via controleerbare stappen.",
            ),
            (
                "Resourcebewaking",
                "resourcebewaking",
                "Ik voeg resourcebewaking toe. Meet GPU, CPU, geheugen en modelduur naast de appstatus, en schakel bij drukte naar kortere beurten of een fallbackmodel.",
            ),
            (
                "Rollback",
                "rollback",
                "Er moet een nuchtere rollbackroute zijn. Houd de laatst werkende binary en backendconfig herkenbaar, zodat teruggaan een expliciete keuze is als een verbetering de cockpit breekt.",
            ),
            (
                "Eigenaarschap",
                "eigenaarschap",
                f"Ik maak eigenaarschap concreet: kies één toetsbaar onderdeel van '{topic_hint}' en lever daarbij resultaat, bewijs en stopconditie in dezelfde beurt.",
            ),
        ]
        if strict:
            options = list(reversed(options))
        ordered = options[seed % len(options):] + options[: seed % len(options)]
        for _label, marker, body in ordered:
            if marker in existing_text:
                continue
            text = prefix + body
            candidate = {
                "round": len(transcript) + 1,
                "phase": phase,
                "participant": self._public_persona(persona),
                "content": text,
            }
            if not self._looks_like_parroting([*transcript, candidate], text):
                return _clip_text(text, 1800)
        action_words = ["meter", "watchdog", "logboek", "herstartpad", "testpoort", "rollback", "wachtrij", "resourcecheck"]
        action = action_words[seed % len(action_words)]
        return _clip_text(
            f"{prefix}Ik pak de {action} op en benoem één meetbaar signaal, één herstelactie en één acceptatiecheck voor '{topic_hint}'.",
            1800,
        )

    def _fallback_summary(self, topic: str, transcript: list[dict[str, Any]], *, meeting_type: str = "team") -> str:
        meeting_type = _normalize_meeting_type(meeting_type)
        topic_intent = _classify_topic_intent(topic)
        names = []
        points = []
        for item in transcript:
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            name = participant.get("name")
            if name and name not in names:
                names.append(str(name))
            if self._is_public_chair(participant):
                continue
            phase = str(item.get("phase") or "")
            if phase in {"floor-control", "intervention"}:
                continue
            content = self._compact_conversation_text(str(item.get("content") or ""), max_words=24).strip()
            if content and content not in points:
                points.append(content)
        workpoints = "; ".join(_clip_text(point, 130) for point in points[:4])
        if workpoints:
            if meeting_type == "development_team":
                topic_hint = _clip_text(topic, 160)
                return (
                    f"Doel: lever een werkbare wijziging voor '{topic_hint}'. "
                    f"Wijzigingen: {workpoints}. "
                    "Acceptatie: het testcommando van De Tester moet groen draaien vanaf een schone state met het verwachte signaal. "
                    "Rollback: revert van de laatste commit of de feature-flag terug op uit. "
                    f"Uitvoerende agent: /codex (of /claude / /roo) na expliciet {APPROVAL_PHRASE}."
                )
            if meeting_type == "sprint_planning":
                if topic_intent == "storing":
                    return (
                        "Incident-sprint: herstel eerst reproduceerbaar en toetsbaar maken. "
                        f"Werkpunten: {workpoints}. "
                        "Acceptatie: foutsignaal, herstelpad, regressietest en rollback zijn zichtbaar. "
                        f"Bouwen of agentuitvoering begint pas na exact {APPROVAL_PHRASE}."
                    )
                if topic_intent == "idee":
                    return (
                        "Prototype-sprint: maak het idee klein genoeg om te leren. "
                        f"Werkpunten: {workpoints}. "
                        "Acceptatie: hypothese, demo, feedbacksignaal en stopvraag zijn benoemd."
                    )
                return (
                    "Sprintdoel: maak de verbetering bouwbaar in kleine taken. "
                    f"Werkpunten: {workpoints}. "
                    "Acceptatie: iedere taak heeft een zichtbaar criterium en test of smoke-run. "
                    f"Bouwen of agentuitvoering begint pas na exact {APPROVAL_PHRASE}."
                )
            if meeting_type == "brainstorm":
                if topic_intent == "opdracht":
                    return (
                        "Samenvatting van de tafel: de eerste bouwstap is read-only meten, niet herstellen. "
                        "We beginnen met read-only health-rollup plus metadata-only telemetry: een `/api/ouroboros/health-rollup` endpoint "
                        "en een JSONL-writer met status, duur, provider, foutcode en timestamp. "
                        "Acceptatie: twee gemiste checks maken alleen de falende laag rood; transcriptinhoud en privédata blijven uit de telemetry. "
                        f"Statuspaneel, herstelcontroller en rollback komen pas daarna aan de beurt, en alleen na {APPROVAL_PHRASE}."
                    )
                if topic_intent == "storing":
                    return (
                        "Diagnosesynthese: de tafel heeft foutsignalen, oorzaken en herstelroutes verkend. "
                        f"Kernlagen: {workpoints}. "
                        "Nog onzeker: welke laag de storing als eerste veroorzaakt. "
                        "Volgend experiment: één reproduceerbare herstelcheck uitvoeren na approval."
                    )
                if topic_intent == "idee":
                    return (
                        "Idee-synthese: de tafel heeft waarde, varianten en prototypes verkend. "
                        f"Kernlagen: {workpoints}. "
                        "Nog onzeker: welke aanname eerst bewezen moet worden. "
                        "Volgend experiment: één prototype met feedbacksignaal ontwerpen."
                    )
                return (
                    "Onderzoekssynthese: de tafel heeft bronlagen, aannames en oplossingsrichtingen verkend. "
                    f"Kernlagen: {workpoints}. "
                    "Nog onzeker: welke bronlaag de doorslag geeft. "
                    "Volgend experiment: test de scherpste aanname lokaal en inspecteerbaar."
                )
            return (
                "Besluit: de cockpit moet zichzelf verbeteren via zichtbare metingen, herstelroutes en tests, niet via verborgen automatische acties. "
                f"Belangrijkste werkpunten: {workpoints}. "
                f"Open risico: bouwen, herstarten of externe acties mogen pas na exact {APPROVAL_PHRASE}. "
                "Volgende stap: kies één eigenaar voor de eerste monitor-test en leg de rollbackroute vast."
            )
        if meeting_type == "development_team":
            topic_hint = _clip_text(topic, 160)
            return (
                f"Doel: lever een werkbare wijziging voor '{topic_hint}'. "
                "Wijzigingen: de tafel moet nog een file/symbol-route en testcommando vaststellen. "
                "Acceptatie: kleinste reproduceerbare test groen vanaf schone state. "
                "Rollback: revert van de laatste commit. "
                f"Uitvoerende agent: /codex (of /claude / /roo) na expliciet {APPROVAL_PHRASE}."
            )
        if meeting_type == "sprint_planning":
            if topic_intent == "storing":
                return (
                    "Incident-sprint: leg eerst reproduceerstap, foutsignaal, herstelpad en regressietest vast. "
                    f"Een agent begint pas met bouwen na exact {APPROVAL_PHRASE}."
                )
            if topic_intent == "idee":
                return (
                    "Prototype-sprint: formuleer hypothese, kleinste demo, feedbacksignaal en stopvraag voordat er gebouwd wordt."
                )
            return (
                "Sprintdoel: formuleer één kleine bouwtaak. "
                "Taken: acceptatiecriterium, testcommando en rollbackroute eerst vastleggen. "
                f"Een agent begint pas met bouwen na exact {APPROVAL_PHRASE}."
            )
        if meeting_type == "brainstorm":
            if topic_intent == "opdracht":
                return (
                    "Samenvatting van de tafel: de eerste bouwstap is read-only meten, niet herstellen. "
                    "We beginnen met read-only health-rollup plus metadata-only telemetry. "
                    "Eerste patch: een `/api/ouroboros/health-rollup` endpoint met JSONL-statusregels. "
                    f"Herstel, rollback en agentbouw beginnen pas na {APPROVAL_PHRASE}."
                )
            if topic_intent == "storing":
                return (
                    "Sterkste inzicht: diagnose gaat voor structurele verbetering. "
                    "Beste richting: foutsignaal, oorzaak en herstelpad isoleren. "
                    "Volgende onderzoeksstap: kies de eerste reproduceerbare check."
                )
            if topic_intent == "idee":
                return (
                    "Sterkste inzicht: het idee heeft eerst waarde, varianten en prototypegrens nodig. "
                    "Beste richting: één leerexperiment voordat er gebouwd wordt."
                )
            return (
                "Sterkste inzicht: eerst bronnen en aannames uit elkaar trekken. "
                "Beste richting: deep search per persona, daarna één experiment per onzekerheid. "
                "Volgende onderzoeksstap: kies de bronlaag die lokaal bewijs kan leveren."
            )
        return (
            "De tafel is het eens dat dit praktisch, controleerbaar en zonder automatische externe acties moet blijven. "
            f"Het grootste risico is onduidelijke eigenaarschap of tool-uitvoering zonder {APPROVAL_PHRASE}. "
            "De eerstvolgende stap is een kleine follow-up formuleren, expliciet een agent kiezen en de bestaande approval-flow gebruiken. "
            f"Voorstel voor vervolgprompt: /agents Werk de vervolgstappen uit voor '{_clip_text(topic, 180)}' "
            f"op basis van de bijdragen van {', '.join(names) if names else 'de persona-deelnemers'}."
        )

    def _public_persona(self, persona: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": persona.get("id"),
            "name": persona.get("name") or persona.get("id"),
            "role": persona.get("role") or "",
            "tone": persona.get("tone") or "",
            "rules": persona.get("rules", []) if isinstance(persona.get("rules"), list) else [],
            "system_prompt": persona.get("system_prompt") or persona.get("instructions") or "",
            "tags": persona.get("tags", []) if isinstance(persona.get("tags"), list) else [],
        }

    def _transcript_text(self, transcript: list[dict[str, Any]]) -> str:
        lines = []
        for item in transcript:
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            name = participant.get("name") or "participant"
            phase = item.get("phase") or "round"
            lines.append(f"[{phase}] {name}: {item.get('content') or ''}")
        return "\n".join(lines)[-12_000:]

    def _knowledge_context(self, persona: dict[str, Any]) -> str:
        snippets = persona.get("_meeting_knowledge") if isinstance(persona.get("_meeting_knowledge"), list) else []
        if not snippets:
            return ""
        blocks = []
        for item in snippets[:14]:
            if not isinstance(item, dict):
                continue
            label = _clip_text(item.get("label") or item.get("source") or "knowledge", 160)
            source = _clip_text(item.get("source") or "", 240)
            snippet = _clip_text(item.get("snippet") or "", 1200)
            if snippet:
                blocks.append(f"- {label} ({source}): {snippet}")
        if not blocks:
            return ""
        return "Beschikbare read-only kenniscontext voor deze persona:\n" + "\n".join(blocks)


class MeetingStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (_default_data_dir() / "meetings")

    def list_meetings(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        records: list[dict[str, Any]] = []
        ids = {path.stem for path in self.directory.glob("*.jsonl")}
        ids.update(path.stem for path in self.directory.glob("*.json"))
        sortable: list[tuple[float, str]] = []
        for meeting_id in ids:
            jsonl_path = self.directory / f"{meeting_id}.jsonl"
            record_path = self._record_path(meeting_id)
            mtimes = [path.stat().st_mtime for path in (jsonl_path, record_path) if path.exists()]
            sortable.append((max(mtimes) if mtimes else 0, meeting_id))
        for updated_ts, meeting_id in sorted(sortable, reverse=True)[:limit]:
            path = self.directory / f"{meeting_id}.jsonl"
            events = self._read_events(path) if path.exists() else []
            event_count = len(events)
            record = self._read_record(meeting_id)
            fallback = self._metadata_from_events(events)
            records.append(
                {
                    "meeting_id": meeting_id,
                    "artifact_path": str(path) if path.exists() else "",
                    "record_path": str(self._record_path(meeting_id)),
                    "event_count": event_count,
                    "topic": record.get("topic") or fallback.get("topic", ""),
                    "meeting_type": record.get("meeting_type") or fallback.get("meeting_type", "team"),
                    "topic_intent": record.get("topic_intent") or fallback.get("topic_intent", ""),
                    "status": record.get("status", "recorded"),
                    "summary": _clip_text(record.get("summary") or fallback.get("summary", ""), 900),
                    "participants": record.get("participants") or fallback.get("participants", []),
                    "agent_ids": record.get("agent_ids") or [],
                    "updated_at": datetime.fromtimestamp(updated_ts, timezone.utc).replace(microsecond=0).isoformat(),
                }
            )
        return records

    def read_meeting(self, meeting_id: str) -> dict[str, Any]:
        clean_id = _safe_slug(meeting_id)
        path = (self.directory / f"{clean_id}.jsonl").resolve()
        try:
            path.relative_to(self.directory.resolve())
        except ValueError as exc:
            raise ValueError("Meeting id escapes meeting directory.") from exc
        events: list[dict[str, Any]] = []
        record = self._read_record(clean_id)
        if not path.exists() and not record:
            raise FileNotFoundError(clean_id)
        if path.exists():
            events = self._read_events(path)
        fallback = self._metadata_from_events(events)
        return {
            "status": record.get("status", "online") if record else "online",
            "meeting_id": clean_id,
            "artifact_path": str(path) if path.exists() else "",
            "record_path": str(self._record_path(clean_id)),
            "events": events,
            "record": record,
            "participants": record.get("participants") or fallback.get("participants", []),
            "rounds": record.get("rounds") or fallback.get("rounds", []),
            "summary": record.get("summary") or fallback.get("summary", ""),
            "topic": record.get("topic") or fallback.get("topic", ""),
            "meeting_type": record.get("meeting_type") or fallback.get("meeting_type", "team"),
            "topic_intent": record.get("topic_intent") or fallback.get("topic_intent", ""),
            "fake_success": False,
        }

    def save_snapshot(self, meeting_id: str, request: MeetingSaveRequest) -> dict[str, Any]:
        clean_id = _safe_slug(meeting_id)
        if _contains_secret_like(_model_to_dict(request)):
            raise ValueError("Meeting snapshot appears to contain a secret, token, password, or bearer credential.")
        existing = self._read_record(clean_id)
        record = {
            **existing,
            "meeting_id": clean_id,
            "frontend_id": request.frontend_id or existing.get("frontend_id", ""),
            "topic": _clip_text(request.topic or existing.get("topic", ""), 4000),
            "meeting_type": _normalize_meeting_type(request.meeting_type or existing.get("meeting_type", "team")),
            "topic_intent": existing.get("topic_intent") or _classify_topic_intent(request.topic or existing.get("topic", "")),
            "participants": request.participants or existing.get("participants", []),
            "participant_ids": request.participant_ids or existing.get("participant_ids", []),
            "agent_ids": request.agent_ids or existing.get("agent_ids", []),
            "rounds": request.rounds or existing.get("rounds", []),
            "summary": _clip_text(request.summary or existing.get("summary", ""), 8000),
            "transcript": _clip_text(request.transcript or existing.get("transcript", ""), MAX_TEXT_CHARS * 2),
            "status": request.status or existing.get("status", "saved"),
            "updated_at": _now_iso(),
            "fake_success": False,
        }
        path = self._write_record(clean_id, record)
        return {"status": "saved", "meeting_id": clean_id, "record": record, "record_path": str(path), "fake_success": False}

    def _meeting_web_queries(self, meeting_type: str, topic: str, persona: dict[str, Any]) -> list[str]:
        meeting_type = _normalize_meeting_type(meeting_type)
        clean_topic = str(topic or "").strip()
        topic_intent = _classify_topic_intent(clean_topic)
        if not clean_topic:
            return []
        if meeting_type == "sprint_planning":
            if topic_intent == "storing":
                return _dedupe_strings(
                    [
                        clean_topic,
                        f"{clean_topic} incident diagnose reproduceerstap logs herstelpad rollback",
                        f"{clean_topic} regressietest smoke test monitoring preventie",
                    ]
                )
            if topic_intent == "idee":
                return _dedupe_strings(
                    [
                        clean_topic,
                        f"{clean_topic} prototype hypothese gebruikersfeedback acceptatiecriteria",
                        f"{clean_topic} sprint planning experiment scope stopregel",
                    ]
                )
            return _dedupe_strings(
                [
                    clean_topic,
                    f"{clean_topic} implementatie acceptatiecriteria testcommando rollback",
                    f"{clean_topic} sprint planning afhankelijkheden stopregel smoke test",
                ]
            )
        if meeting_type == "brainstorm":
            persona_lens = " ".join(
                str(part).strip()
                for part in (persona.get("name"), persona.get("role"))
                if str(part or "").strip()
            )
            if topic_intent == "opdracht":
                return _dedupe_strings(
                    [
                        clean_topic,
                        f"{clean_topic} implementatie architectuur ontwerpkeuzes acceptatiecriteria",
                        f"{clean_topic} monitoring observability smoke test rollback",
                        f"{clean_topic} {persona_lens} perspectief randvoorwaarden risico's failure modes",
                        f"{clean_topic} vergelijkbare systemen best practices implementatiepatronen",
                        f"{clean_topic} aannames alternatieven tegenvoorbeelden experimenten",
                    ]
                )
            if topic_intent == "storing":
                return _dedupe_strings(
                    [
                        clean_topic,
                        f"{clean_topic} incident diagnose logs foutsignalen herstelpad",
                        f"{clean_topic} technische lagen failure modes recovery rollback",
                        f"{clean_topic} {persona_lens} perspectief reproduceren monitoren voorkomen",
                        f"{clean_topic} vergelijkbare storingen best practices monitoring",
                        f"{clean_topic} aannames alternatieven tegenvoorbeelden experimenten",
                    ]
                )
            if topic_intent == "idee":
                return _dedupe_strings(
                    [
                        clean_topic,
                        f"{clean_topic} concept voorbeelden alternatieven gebruikerswaarde prototype",
                        f"{clean_topic} ontwerpvarianten randvoorwaarden evaluatie experiment",
                        f"{clean_topic} {persona_lens} perspectief risico's failure modes",
                        f"{clean_topic} vergelijkbare systemen best practices",
                        f"{clean_topic} aannames alternatieven tegenvoorbeelden experimenten",
                    ]
                )
            return _dedupe_strings(
                [
                    clean_topic,
                    f"{clean_topic} bronnen onderzoek risico's alternatieven",
                    f"{clean_topic} technische lagen ontwerp implementatie bewijs",
                    f"{clean_topic} {persona_lens} perspectief failure modes ontwerpkeuzes",
                    f"{clean_topic} vergelijkbare systemen best practices monitoring recovery testing",
                    f"{clean_topic} aannames alternatieven tegenvoorbeelden experimenten",
                ]
            )
        return [clean_topic]

    def create_meeting(
        self,
        request: MeetingRequest,
        persona_store: PersonaStore,
        llm_call: MeetingLLMCall | None = None,
        knowledge_store: KnowledgeStore | None = None,
        web_context_fetcher: Callable[[dict[str, Any], str], list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        prep = self._prepare_meeting_run(
            request,
            persona_store=persona_store,
            knowledge_store=knowledge_store,
            web_context_fetcher=web_context_fetcher,
        )
        if prep.get("blocked"):
            return prep["blocked"]
        meeting_id = prep["meeting_id"]
        meeting_type = prep["meeting_type"]
        provider = prep["provider"]
        model = prep["model"]
        events: list[dict[str, Any]] = [prep["started_event"]]

        runner_payload = MeetingRunner(llm_call=llm_call).run(
            topic=request.topic,
            personas=prep["personas"],
            provider=provider,
            model=model,
            meeting_id=meeting_id,
            meeting_type=meeting_type,
        )
        events.extend(runner_payload["events"])
        return self._finalize_meeting_run(
            request=request,
            prep=prep,
            events=events,
            runner_payload=runner_payload,
        )

    def stream_meeting(
        self,
        request: MeetingRequest,
        persona_store: PersonaStore,
        llm_call: MeetingLLMCall | None = None,
        knowledge_store: KnowledgeStore | None = None,
        web_context_fetcher: Callable[[dict[str, Any], str], list[dict[str, Any]]] | None = None,
    ) -> "Iterator[dict[str, Any]]":
        """Generator that yields meeting events live and persists artifacts at the end.

        The first yielded event is the `meeting_started` envelope (same shape as
        `create_meeting`'s first event). For every event produced by the runner an
        intermediate envelope is yielded immediately. The final event is a
        `meeting_recorded` envelope containing the persisted summary, transcript and
        artifact path.
        """
        prep = self._prepare_meeting_run(
            request,
            persona_store=persona_store,
            knowledge_store=knowledge_store,
            web_context_fetcher=web_context_fetcher,
        )
        if prep.get("blocked"):
            yield prep["blocked"]
            return

        meeting_id = prep["meeting_id"]
        meeting_type = prep["meeting_type"]
        provider = prep["provider"]
        model = prep["model"]
        personas_for_run = prep["personas"]
        topic_intent = prep["topic_intent"]
        started_event = prep["started_event"]
        events: list[dict[str, Any]] = [started_event]

        yield started_event

        sentinel: dict[str, Any] = {"type": "__meeting_stream_done__"}
        queue: "Queue[dict[str, Any]]" = Queue()
        runner = MeetingRunner(llm_call=llm_call)
        captured_payload: dict[str, Any] = {}
        runner_error: dict[str, BaseException | None] = {"error": None}

        def _run() -> None:
            try:
                captured_payload["payload"] = runner.run(
                    topic=request.topic,
                    personas=personas_for_run,
                    provider=provider,
                    model=model,
                    meeting_id=meeting_id,
                    meeting_type=meeting_type,
                    event_sink=queue.put,
                )
            except BaseException as exc:  # pragma: no cover - protective
                runner_error["error"] = exc
            finally:
                queue.put(sentinel)

        thread = threading.Thread(target=_run, name="meeting-stream-runner", daemon=True)
        thread.start()
        try:
            while True:
                event = queue.get()
                if event is sentinel:
                    break
                events.append(event)
                yield event
        finally:
            thread.join()

        error = runner_error["error"]
        if error is not None:
            yield {
                "type": "meeting_error",
                "meeting_id": meeting_id,
                "timestamp": _now_iso(),
                "error": str(error),
            }
            return

        runner_payload = captured_payload.get("payload") or {
            "meeting_type": meeting_type,
            "topic_intent": topic_intent,
            "participants": [self._public_persona_for_participant(p) for p in personas_for_run],
            "rounds": [event for event in events if event.get("type") == "participant_turn"],
            "summary": "",
            "events": events[1:],
        }
        finalized = self._finalize_meeting_run(
            request=request,
            prep=prep,
            events=events,
            runner_payload=runner_payload,
        )
        yield {
            "type": "meeting_recorded",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "status": finalized.get("status"),
            "artifact_path": finalized.get("artifact_path"),
            "record_path": finalized.get("record_path"),
            "event_count": finalized.get("event_count"),
            "meeting_type": finalized.get("meeting_type"),
            "topic_intent": finalized.get("topic_intent"),
            "participants": finalized.get("participants"),
            "rounds": finalized.get("rounds"),
            "summary": finalized.get("summary"),
            "transcript": finalized.get("transcript"),
            "build_prompt": finalized.get("build_prompt", ""),
            "tool_policy": finalized.get("tool_policy"),
            "fake_success": False,
        }

    def _public_persona_for_participant(self, persona: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": persona.get("id"),
            "name": persona.get("name") or persona.get("id"),
            "role": persona.get("role") or "",
        }

    def _prepare_meeting_run(
        self,
        request: MeetingRequest,
        *,
        persona_store: PersonaStore,
        knowledge_store: KnowledgeStore | None,
        web_context_fetcher: Callable[[dict[str, Any], str], list[dict[str, Any]]] | None,
    ) -> dict[str, Any]:
        requested_tools = [str(item).strip() for item in request.tools if str(item).strip()]
        forbidden = [
            tool
            for tool in requested_tools
            if any(marker in tool.lower() for marker in MEETING_FORBIDDEN_TOOL_MARKERS)
        ]
        if request.allow_tools or requested_tools:
            return {
                "blocked": {
                    "status": "blocked",
                    "reason": "Ouroboros chat meetings are transcript-only and do not execute Cline, shell, browser, or write tools.",
                    "requested_tools": requested_tools,
                    "forbidden_tools": forbidden,
                    "tool_policy": self.tool_policy(),
                    "approval_phrase": APPROVAL_PHRASE,
                    "fake_success": False,
                }
            }
        if _contains_secret_like({"topic": request.topic, "participants": request.participants}):
            raise ValueError("Meeting content appears to contain a secret, token, password, or bearer credential.")

        meeting_type = _normalize_meeting_type(request.meeting_type)
        topic_intent = _classify_topic_intent(request.topic)
        if meeting_type == "development_team":
            personas = _default_development_team_personas()
        else:
            participants = request.participants or ["ouroboros"]
            personas = []
            for persona_id in participants[:12]:
                persona = persona_store.get(persona_id)
                persona = persona or {"id": _safe_slug(persona_id), "name": str(persona_id), "description": "", "tags": []}
                persona = dict(persona)
                policy = enforce_tool_policy(persona)
                knowledge: list[dict[str, Any]] = []
                if knowledge_store is not None and policy.get("can_search_files"):
                    knowledge.extend(knowledge_store.snippets_for_persona(persona, request.topic, limit=3))
                if web_context_fetcher is not None and policy.get("can_search_web"):
                    web_queries = self._meeting_web_queries(meeting_type, request.topic, persona)
                    for query in web_queries:
                        knowledge.extend(web_context_fetcher(persona, query)[:2])
                if knowledge:
                    if meeting_type == "brainstorm":
                        knowledge_limit = 14
                    elif meeting_type == "sprint_planning":
                        knowledge_limit = 8
                    else:
                        knowledge_limit = 5
                    persona["_meeting_knowledge"] = self._dedupe_knowledge(knowledge)[:knowledge_limit]
                personas.append(persona)

        meeting_id = f"{int(time.time())}-{uuid.uuid4().hex[:10]}"
        provider = (request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        model = (request.model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        started_event = {
            "type": "meeting_started",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "topic": _clip_text(request.topic, 2000),
            "meeting_type": meeting_type,
            "meeting_type_label": MEETING_TYPE_LABELS.get(meeting_type, MEETING_TYPE_LABELS["team"]),
            "topic_intent": topic_intent,
            "topic_intent_label": _topic_intent_label(topic_intent),
            "provider": provider,
            "model": model,
            "approval_phrase": APPROVAL_PHRASE,
            "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
            "tool_policy": self.tool_policy(),
            "safety_note": (
                "No Cline execution, shell commands, browser control, agent execution, or write tools were run."
            ),
            "participants": [self._public_persona_for_participant(persona) for persona in personas],
        }
        return {
            "meeting_id": meeting_id,
            "meeting_type": meeting_type,
            "topic_intent": topic_intent,
            "provider": provider,
            "model": model,
            "personas": personas,
            "started_event": started_event,
        }

    def _finalize_meeting_run(
        self,
        *,
        request: MeetingRequest,
        prep: dict[str, Any],
        events: list[dict[str, Any]],
        runner_payload: dict[str, Any],
    ) -> dict[str, Any]:
        meeting_id = prep["meeting_id"]
        meeting_type = prep["meeting_type"]
        topic_intent = prep["topic_intent"]
        provider = prep["provider"]
        model = prep["model"]
        path = self._write_events(meeting_id, events)
        transcript = self._transcript_from_runner(runner_payload)
        build_prompt = self._extract_build_prompt(meeting_type, request, runner_payload)
        build_plan: dict[str, Any] | None = None
        if build_prompt:
            try:
                parsed_plan = json.loads(build_prompt)
            except Exception:
                parsed_plan = None
            if isinstance(parsed_plan, dict):
                build_plan = _normalize_build_plan(parsed_plan, fallback_title=request.topic)
        self._write_record(
            meeting_id,
            {
                "meeting_id": meeting_id,
                "topic": _clip_text(request.topic, 4000),
                "meeting_type": meeting_type,
                "topic_intent": runner_payload.get("topic_intent") or topic_intent,
                "participants": runner_payload["participants"],
                "participant_ids": [str(item.get("id")) for item in runner_payload["participants"] if item.get("id")],
                "agent_ids": [],
                "rounds": runner_payload["rounds"],
                "summary": runner_payload["summary"],
                "transcript": transcript,
                "build_prompt": build_prompt,
                "build_plan": build_plan,
                "status": "completed",
                "provider": provider,
                "model": model,
                "artifact_path": str(path),
                "created_at": events[0]["timestamp"],
                "updated_at": _now_iso(),
                "tool_policy": self.tool_policy(),
                "fake_success": False,
            },
        )
        return {
            "status": "recorded",
            "meeting_id": meeting_id,
            "artifact_path": str(path),
            "record_path": str(self._record_path(meeting_id)),
            "event_count": len(events),
            "meeting_type": meeting_type,
            "topic_intent": runner_payload.get("topic_intent") or topic_intent,
            "events": events,
            "participants": runner_payload["participants"],
            "rounds": runner_payload["rounds"],
            "summary": runner_payload["summary"],
            "transcript": transcript,
            "build_prompt": build_prompt,
            "build_plan": build_plan,
            "tool_policy": self.tool_policy(),
            "fake_success": False,
        }

    def _extract_build_prompt(self, meeting_type: str, request: MeetingRequest, runner_payload: dict[str, Any]) -> str:
        """Compose a deterministic BUILD_PLAN JSON object from the dev-team transcript."""
        if _normalize_meeting_type(meeting_type) != "development_team":
            return ""
        rounds = [item for item in (runner_payload.get("rounds") or []) if isinstance(item, dict)]
        summary = str(runner_payload.get("summary") or "").strip()

        transcript_lines: list[str] = []
        designer_notes: list[str] = []
        developer_notes: list[str] = []
        tester_notes: list[str] = []
        critic_notes: list[str] = []
        for item in rounds:
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            participant_name = str(participant.get("name") or participant.get("id") or "Deelnemer")
            participant_id = str(participant.get("id") or "").lower()
            phase = str(item.get("phase") or "").lower()
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            line = f"{participant_name}: {content}"
            transcript_lines.append(line)
            role_key = f"{participant_id} {participant_name.lower()} {phase}"
            if "ontwerper" in role_key or "designer" in role_key or "design" in role_key:
                designer_notes.append(content)
            elif "developer" in role_key or "developper" in role_key or "implementation" in role_key:
                developer_notes.append(content)
            elif "tester" in role_key or "test" in role_key:
                tester_notes.append(content)
            elif "criticus" in role_key or "critic" in role_key:
                critic_notes.append(content)

        combined = "\n".join([summary, *transcript_lines]).strip()
        for candidate in (summary, combined):
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end <= start:
                continue
            try:
                parsed = json.loads(candidate[start : end + 1])
            except Exception:
                continue
            if isinstance(parsed, dict) and any(key in parsed for key in ("title", "goals", "components", "tests", "constraints")):
                return json.dumps(_normalize_build_plan(parsed, fallback_title=request.topic), ensure_ascii=False, indent=2)

        title = _clip_text(str(request.topic or "Ouroboros build").strip(), 160)
        goals = _dedupe_strings(
            [
                title,
                *[
                    _clip_text(sentence.strip(), 240)
                    for sentence in re.split(r"(?<=[.!?])\s+", combined)
                    if sentence.strip().lower().startswith(("na deze build", "doel", "bouw", "voeg", "maak", "implementeer"))
                ],
            ]
        )[:5]
        if not goals:
            goals = [title]

        file_pattern = re.compile(r"`([^`]+\.[A-Za-z0-9]{1,8})`|((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8})")
        components: list[dict[str, str]] = []
        seen_components: set[str] = set()
        for note in developer_notes or designer_notes or transcript_lines:
            for match in file_pattern.finditer(note):
                path = (match.group(1) or match.group(2) or "").strip()
                if not path or path in seen_components:
                    continue
                seen_components.add(path)
                components.append({"name": path, "description": _clip_text(note, 220)})
        if not components:
            components.append(
                {
                    "name": "implementation",
                    "description": _clip_text(developer_notes[0] if developer_notes else title, 220),
                }
            )

        tests = _dedupe_strings(
            [
                _clip_text(line.strip(" -"), 240)
                for note in tester_notes
                for line in note.splitlines()
                if any(marker in line.lower() for marker in ("pytest", "python -m", "npm test", "testcommando", "<cmd", "verwacht"))
            ]
        )[:6]
        if not tests:
            tests = ["Draai het kleinste relevante testcommando en verwacht exitcode 0."]

        constraints = _dedupe_strings(
            [
                "Geen automatische externe acties zonder expliciet Akkoord.",
                "Wijzig alleen de afgesproken sandbox/workspace files.",
                *[
                    _clip_text(line.strip(" -"), 240)
                    for note in critic_notes
                    for line in note.splitlines()
                    if any(marker in line.lower() for marker in ("blocker", "warning", "risico", "rollback", "constraint"))
                ],
            ]
        )[:8]
        plan = {
            "title": title,
            "goals": goals,
            "components": components[:8],
            "tests": tests,
            "constraints": constraints,
        }
        return json.dumps(plan, ensure_ascii=False, indent=2)
        # Cleaned up old unused fallback logic.

    def _dedupe_knowledge(self, knowledge: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in knowledge:
            if not isinstance(item, dict):
                continue
            key = f"{item.get('source') or ''}:{str(item.get('snippet') or '')[:180]}"
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def tool_policy(self) -> dict[str, Any]:
        return {
            "mode": "no_tools",
            "cline_execution": False,
            "shell": False,
            "browser": False,
            "write_tools": False,
            "read_only_web_context": "persona_brave_search_when_enabled",
            "artifact_write": "jsonl_and_json_snapshot",
        }

    def _write_events(self, meeting_id: str, events: list[dict[str, Any]]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = (self.directory / f"{_safe_slug(meeting_id)}.jsonl").resolve()
        try:
            path.relative_to(self.directory.resolve())
        except ValueError as exc:
            raise ValueError("Meeting artifact path escapes meeting directory.") from exc
        with path.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def _record_path(self, meeting_id: str) -> Path:
        return (self.directory / f"{_safe_slug(meeting_id)}.json").resolve()

    def _read_record(self, meeting_id: str) -> dict[str, Any]:
        path = self._record_path(meeting_id)
        try:
            path.relative_to(self.directory.resolve())
        except ValueError:
            return {}
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _read_events(self, path: Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    events.append(item)
        except Exception:
            return events
        return events

    def _metadata_from_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        participants_by_id: dict[str, dict[str, Any]] = {}
        rounds: list[dict[str, Any]] = []
        topic = ""
        meeting_type = "team"
        topic_intent = ""
        summary = ""
        for index, event in enumerate(events):
            event_type = str(event.get("type") or "")
            if event_type == "meeting_started":
                topic = topic or str(event.get("topic") or "")
                meeting_type = _normalize_meeting_type(event.get("meeting_type") or meeting_type)
                topic_intent = str(event.get("topic_intent") or topic_intent or "")
                continue
            participant = event.get("participant") if isinstance(event.get("participant"), dict) else {}
            if participant:
                participant_id = str(participant.get("id") or participant.get("name") or f"participant-{index}")
                participants_by_id.setdefault(
                    participant_id,
                    {
                        "id": participant_id,
                        "name": str(participant.get("name") or participant_id),
                        "role": str(participant.get("role") or ""),
                        "tone": str(participant.get("tone") or ""),
                        "rules": participant.get("rules", []) if isinstance(participant.get("rules"), list) else [],
                        "tags": participant.get("tags", []) if isinstance(participant.get("tags"), list) else [],
                    },
                )
            if event_type in {"participant_turn", "participant_note"}:
                rounds.append(event)
                continue
            if event_type == "meeting_summary":
                summary = str(event.get("summary") or event.get("content") or "")
        return {
            "topic": _clip_text(topic, 4000),
            "meeting_type": meeting_type,
            "topic_intent": topic_intent or _classify_topic_intent(topic),
            "participants": list(participants_by_id.values()),
            "rounds": rounds,
            "summary": _clip_text(summary, 8000),
        }

    def _write_record(self, meeting_id: str, record: dict[str, Any]) -> Path:
        if _contains_secret_like(record):
            raise ValueError("Meeting record write blocked because content appears to contain a secret.")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._record_path(meeting_id)
        try:
            path.relative_to(self.directory.resolve())
        except ValueError as exc:
            raise ValueError("Meeting record path escapes meeting directory.") from exc
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def _transcript_from_runner(self, runner_payload: dict[str, Any]) -> str:
        parts = []
        for turn in runner_payload.get("rounds", []):
            participant = turn.get("participant") if isinstance(turn.get("participant"), dict) else {}
            name = participant.get("name") or "Persona"
            parts.append(f"{name} (ronde {turn.get('round')} / {turn.get('phase')}):\n{turn.get('content', '')}")
        if runner_payload.get("summary"):
            parts.append(f"Consensus & Actiepunten:\n{runner_payload['summary']}")
        return "\n\n---\n\n".join(parts)


class OuroborosChatService:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        cline_root: Path | None = None,
        ollama_client: Any | None = None,
        ollama_timeout_seconds: float | None = None,
    ):
        self.data_dir = data_dir or _default_data_dir()
        self.cline_root = (cline_root or CLINE_ROOT).expanduser()
        self.ollama_client = ollama_client
        self.ollama_timeout_seconds = float(
            ollama_timeout_seconds if ollama_timeout_seconds is not None else os.getenv("WINTRIP_OUROBOROS_CHAT_OLLAMA_TIMEOUT", "45")
        )
        self.personas = PersonaStore(self.data_dir / "personas.json")
        self.meetings = MeetingStore(self.data_dir / "meetings")
        self.conversations = ConversationStore(self.data_dir / "conversations")
        self.memory = MemoryStore(self.data_dir / "memory.json")
        self.knowledge = KnowledgeStore()
        self.prompt_assembler = PromptAssembler()
        self.uploads_dir = self.data_dir / "uploads"

    def create_meeting(self, request: MeetingRequest) -> dict[str, Any]:
        return self.meetings.create_meeting(
            request,
            self.personas,
            llm_call=self._call_model_provider,
            knowledge_store=self.knowledge,
            web_context_fetcher=self._brave_knowledge_for_persona,
        )

    def stream_meeting(self, request: MeetingRequest) -> Iterator[dict[str, Any]]:
        return self.meetings.stream_meeting(
            request,
            self.personas,
            llm_call=self._call_model_provider,
            knowledge_store=self.knowledge,
            web_context_fetcher=self._brave_knowledge_for_persona,
        )

    def stream_development_team(self, request: DevelopmentTeamRequest) -> Iterator[dict[str, Any]]:
        """Stream an isolated Development Team planning session with the five fixed roles."""
        if _contains_secret_like({"prompt": request.prompt, "persona_ids": request.persona_ids, "agent_ids": request.agent_ids}):
            raise ValueError("Development-team prompt appears to contain a secret, token, password, or bearer credential.")

        provider = str(request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        requested_model = str(request.model or "").strip()
        model_hints = CODING_MODEL_HINTS.get(provider, ())
        model = requested_model or (model_hints[0] if model_hints else DEFAULT_MODEL)
        topic, _clarifications = self._development_team_topic(request)
        if _development_team_planning_strategy() == "deterministic":
            yield from self._stream_fast_development_team_plan(
                request=request,
                topic=topic,
                provider=provider,
                model=model,
            )
            return
        meeting_request = MeetingRequest(
            topic=topic,
            meeting_type="development_team",
            participants=list(DEV_TEAM_DEFAULT_PERSONA_IDS),
            provider=provider,
            model=model,
            tools=[],
            allow_tools=False,
        )
        yield from self.stream_meeting(meeting_request)

    def _stream_fast_development_team_plan(
        self,
        *,
        request: DevelopmentTeamRequest,
        topic: str,
        provider: str,
        model: str,
    ) -> Iterator[dict[str, Any]]:
        """Fast no-LLM planning pass for the separated five-role Development Team."""
        meeting_id = f"{int(time.time())}-{uuid.uuid4().hex[:10]}"
        participants = _public_development_team_agents()
        participants_by_id = {str(item.get("id") or ""): item for item in participants}
        build_plan = _development_team_seed_plan(topic)
        build_prompt = json.dumps(build_plan, ensure_ascii=False, indent=2)
        started_event = {
            "type": "meeting_started",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "topic": _clip_text(topic, 2000),
            "meeting_type": "development_team",
            "meeting_type_label": MEETING_TYPE_LABELS.get("development_team", "Ontwikkelteam-vergadering"),
            "topic_intent": _classify_topic_intent(topic),
            "topic_intent_label": _topic_intent_label(_classify_topic_intent(topic)),
            "provider": provider,
            "model": model,
            "approval_phrase": APPROVAL_PHRASE,
            "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
            "tool_policy": self.meetings.tool_policy(),
            "planning_strategy": "deterministic",
            "communication_protocol": {
                "name": "gas-town-nudge-mail-handoff",
                "source": str(GASTOWN_ROOT),
                "fields": ["MODE", "FROM", "TO", "SUBJECT", "BODY", "NEXT"],
            },
            "safety_note": "No Cline execution, shell commands, browser control, agent execution, or write tools were run.",
            "participants": participants,
        }
        events: list[dict[str, Any]] = [started_event]
        yield started_event

        def turn(persona_id: str, round_number: int, phase: str, content: str) -> dict[str, Any]:
            participant = participants_by_id.get(persona_id) or {"id": persona_id, "name": persona_id, "role": ""}
            return {
                "type": "participant_turn",
                "meeting_id": meeting_id,
                "timestamp": _now_iso(),
                "meeting_type": "development_team",
                "round": round_number,
                "phase": phase,
                "participant": participant,
                "content": content,
                "provider": provider,
                "model": model,
                "ok": True,
                "error": "",
                "prompt_context": {
                    "deterministic_planning": True,
                    "gas_town_protocol": "nudge/mail/handoff",
                    "llm_call_made": False,
                },
            }

        turns = [
            turn(
                "dev-voorman",
                1,
                "triage",
                _gastown_agent_message(
                    mode="nudge",
                    sender="Voorman",
                    recipient="Ontwerper",
                    subject="bouwdoel en werkgrens",
                    body=(
                        f"Bouwdoel: {build_plan['title']}\n"
                        f"Goals: {'; '.join(build_plan.get('goals', [])[:3])}\n"
                        "Werk klein: maak één formeel build_plan dat de build-loop direct kan uitvoeren."
                    ),
                    next_action="Ontwerper legt files, interface en testhook vast.",
                ),
            ),
            turn(
                "dev-ontwerper",
                1,
                "design-contract",
                _gastown_agent_message(
                    mode="nudge",
                    sender="Ontwerper",
                    recipient="De Developper",
                    subject="ontwerpcontract",
                    body=(
                        f"CONTRACT: {build_plan['title']}\n"
                        f"FILES: {', '.join(component['name'] for component in build_plan.get('components', [])[:5])}\n"
                        "INTERFACE: houd input/output direct observeerbaar.\n"
                        f"TEST_HOOK: {build_plan.get('tests', [''])[0]}"
                    ),
                    next_action="De Developper gebruikt dit build_plan als startcontract in de gescheiden build-loop.",
                ),
            ),
            turn(
                "dev-developper",
                1,
                "implementation-route",
                _gastown_agent_message(
                    mode="nudge",
                    sender="De Developper",
                    recipient="De Tester",
                    subject="kleinste editroute",
                    body=(
                        "Ik raak alleen sandbox/workspace-bestanden die uit het build_plan volgen. "
                        "Ik schrijf kleine Aider-style diff/file blokken en geef daarna één testoverdracht."
                    ),
                    next_action="De Tester kiest het kleinste acceptance-commando.",
                ),
            ),
            turn(
                "dev-tester",
                1,
                "test-plan",
                _gastown_agent_message(
                    mode="nudge",
                    sender="De Tester",
                    recipient="Critikus",
                    subject="acceptatiebewijs",
                    body=(
                        f"Primair testbewijs: {build_plan.get('tests', [''])[0]}\n"
                        "Groen betekent exitcode 0 plus zichtbaar bewijs voor het beschreven doel."
                    ),
                    next_action="Critikus benoemt alleen concrete blockers of accepteert met waarschuwing.",
                ),
            ),
            turn(
                "dev-critikus",
                1,
                "risk-review",
                _gastown_agent_message(
                    mode="mail",
                    sender="Critikus",
                    recipient="Voorman/De Developper/De Tester",
                    subject="blockers en grenzen",
                    body=(
                        "Blocker: geen fake success. Warning: als het gekozen model traag is, laat alleen de Developper-call zwaar zijn. "
                        "Alle ondersteunende rollen moeten via vaste Gas Town-overdracht blijven communiceren."
                    ),
                    next_action="Voorman zet het definitieve build_plan klaar voor OUROBOROS DEVELOPMENT TEAM.",
                ),
            ),
            turn(
                "dev-voorman",
                2,
                "handoff",
                _gastown_agent_message(
                    mode="handoff",
                    sender="Voorman",
                    recipient="OUROBOROS DEVELOPMENT TEAM build-loop",
                    subject="formeel build_plan",
                    body=f"BUILD_PLAN_JSON:\n{build_prompt}",
                    next_action="Start de gescheiden build-loop: Voorman -> Ontwerper -> Developper -> Tester -> Critikus.",
                ),
            ),
        ]

        for event in turns:
            events.append(event)
            yield event

        summary = (
            "Ontwikkelteam-plan staat klaar met vijf gescheiden rollen. "
            "Onderlinge communicatie gebruikt Gas Town MODE: nudge/mail/handoff; de build-loop kan nu met één zware Developper-call per iteratie werken."
        )
        summary_event = {
            "type": "meeting_summary",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "meeting_type": "development_team",
            "topic_intent": _classify_topic_intent(topic),
            "content": summary,
            "summary": summary,
            "provider": provider,
            "model": model,
            "ok": True,
            "error": "",
            "safety_note": "No Cline execution, shell commands, browser control, agent execution, or write tools were run.",
            "next_action": "Gebruik het build_plan in /api/ouroboros-chat/development-team/build/stream.",
        }
        events.append(summary_event)
        yield summary_event

        transcript = "\n\n".join(
            f"{event.get('participant', {}).get('name')}: {event.get('content')}"
            for event in turns
        )
        event_path = self.meetings._write_events(meeting_id, events)
        record_path = self.meetings._write_record(
            meeting_id,
            {
                "meeting_id": meeting_id,
                "topic": _clip_text(topic, 4000),
                "meeting_type": "development_team",
                "topic_intent": _classify_topic_intent(topic),
                "participants": participants,
                "participant_ids": [str(item.get("id")) for item in participants if item.get("id")],
                "agent_ids": request.agent_ids or [],
                "rounds": turns,
                "summary": summary,
                "transcript": transcript,
                "build_prompt": build_prompt,
                "build_plan": build_plan,
                "status": "completed",
                "provider": provider,
                "model": model,
                "artifact_path": str(event_path),
                "created_at": started_event["timestamp"],
                "updated_at": _now_iso(),
                "tool_policy": self.meetings.tool_policy(),
                "planning_strategy": "deterministic",
                "fake_success": False,
            },
        )
        yield {
            "type": "meeting_recorded",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "status": "recorded",
            "artifact_path": str(event_path),
            "record_path": str(record_path),
            "event_count": len(events),
            "meeting_type": "development_team",
            "topic_intent": _classify_topic_intent(topic),
            "participants": participants,
            "rounds": turns,
            "summary": summary,
            "transcript": transcript,
            "build_prompt": build_prompt,
            "build_plan": build_plan,
            "tool_policy": self.meetings.tool_policy(),
            "planning_strategy": "deterministic",
            "fake_success": False,
        }

    def development_team_intake(self, request: DevelopmentTeamIntakeRequest) -> dict[str, Any]:
        """Single chair-LLM call that decides whether the user's prompt needs clarification.

        Returns either {"needs_clarification": False, "questions": []} or
        {"needs_clarification": True, "questions": [...]} so the FE can put a short Q&A in
        front of the actual development_team meeting. Keeps the meeting itself focused.

        The intake question is a simple yes/no JSON decision and does not benefit from a heavy
        coding model. To avoid a cold-start delay of 30-60s on `devstral:latest` and friends,
        we force the intake call onto a fast lightweight model (`ouroboros:latest` by default
        — overridable via WINTRIP_DEVTEAM_INTAKE_MODEL). The user's chosen model is preserved
        for the actual development meeting and build loop.
        """
        if _contains_secret_like({"prompt": request.prompt}):
            raise ValueError("Development-team intake prompt appears to contain a secret, token, password, or bearer credential.")

        provider = str(request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        # Override the model for intake: always a fast small Ollama model unless the user
        # is on a cloud provider (where cold-start isn't a concern in the same way).
        if provider in {DEFAULT_PROVIDER, "ollama", "local", "ouroboros"}:
            model = os.getenv("WINTRIP_DEVTEAM_INTAKE_MODEL", "ouroboros:latest").strip() or "ouroboros:latest"
            provider = DEFAULT_PROVIDER
        else:
            requested_model = str(request.model or "").strip()
            model_hints = CODING_MODEL_HINTS.get(provider, ())
            model = requested_model or (model_hints[0] if model_hints else DEFAULT_MODEL)

        intake_system_prompt = (
            "Je bent Voorman van het gescheiden Ouroboros-ontwikkelteam. Je MOET ALTIJD beginnen met verduidelijkingsvragen voordat het team begint met bouwen.\n"
            "Stel EXACT 3 verduidelijkingsvragen over scope, gewenste UI/CLI, doelgroep of expliciete acceptatiecriteria. "
            "Daarnaast MOET je als 4e vraag altijd vragen in welke specifieke map/directory de applicatie moet worden opgeslagen (bijv. in /home/pwintri2/...) als het een nieuwe applicatie betreft.\n\n"
            "Antwoord uitsluitend in JSON, zonder markdown, zonder toelichting. Je antwoord MOET in de volgende vorm zijn:\n"
            "{\"needs_clarification\": true, \"questions\": [\"vraag 1?\", \"vraag 2?\", \"vraag 3?\", \"In welke directory moet dit worden opgeslagen?\"]}\n"
            "Precies 4 vragen. Elke vraag is kort, concreet en eindigt met een vraagteken."
        )
        intake_user_prompt = (
            "Ontwikkelopdracht van de gebruiker:\n"
            f"{_clip_text(request.prompt, 2400)}\n\n"
            "Beoordeel de opdracht en lever de JSON."
        )
        timeout_seconds = _development_team_intake_timeout_seconds()
        response: dict[str, Any] | None = None
        fallback_reason = ""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="devteam-intake")
        future = executor.submit(
            self._call_model_provider,
            prompt=intake_user_prompt,
            provider=provider,
            model=model,
            system_prompt=intake_system_prompt,
            history=[],
        )
        try:
            maybe_response = future.result(timeout=timeout_seconds)
            response = maybe_response if isinstance(maybe_response, dict) else {"content": str(maybe_response or "")}
        except concurrent.futures.TimeoutError:
            future.cancel()
            fallback_reason = f"intake_model_timeout_after_{timeout_seconds:.1f}s"
        except Exception as exc:  # noqa: BLE001 - intake should never block the UI flow
            fallback_reason = f"intake_model_error: {exc}"
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        parsed = _parse_intake_response(response.get("content") if response else "")
        if not parsed["questions"]:
            parsed = {
                "needs_clarification": True,
                "questions": _fallback_development_team_intake_questions(request.prompt),
            }
            fallback_reason = fallback_reason or "intake_model_returned_no_questions"
        return {
            "status": "intake_complete",
            "needs_clarification": parsed["needs_clarification"],
            "questions": parsed["questions"][:4],
            "prompt": _clip_text(request.prompt, 3000),
            "provider": (response or {}).get("provider", provider),
            "model": (response or {}).get("model", model),
            "raw": _clip_text(str((response or {}).get("content") or fallback_reason), 1600),
            "fallback_used": bool(fallback_reason),
            "fallback_reason": fallback_reason,
            "fake_success": False,
        }

    def development_team(self, request: DevelopmentTeamRequest) -> dict[str, Any]:
        """Run a real `development_team` meeting and surface a workable build prompt.

        Replaces the old templated rounds with fixed five-role collaboration: Voorman
        keeps the goal in view, Ontwerper fixes the contract, De Developper proposes concrete
        files/symbols, De Tester delivers an acceptance command + rollback, Critikus catches risks. The
        deterministic build-prompt compositor turns the transcript into a slash-command
        that the agent-runtime can execute inside its Docker-isolated job.
        """
        if _contains_secret_like({"prompt": request.prompt, "persona_ids": request.persona_ids, "agent_ids": request.agent_ids}):
            raise ValueError("Development-team prompt appears to contain a secret, token, password, or bearer credential.")

        provider = str(request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        requested_model = str(request.model or "").strip()
        model_hints = CODING_MODEL_HINTS.get(provider, ())
        model = requested_model or (model_hints[0] if model_hints else DEFAULT_MODEL)
        max_iterations = max(1, min(int(getattr(request, "max_iterations", 3) or 3), 8))
        persona_ids = list(request.persona_ids) if request.persona_ids else list(DEV_TEAM_DEFAULT_PERSONA_IDS)
        agent_ids = request.agent_ids or ["codex"]

        # Augment topic with any clarification Q&A from a preceding intake step.
        topic, clarifications = self._development_team_topic(request)

        if _development_team_planning_strategy() == "deterministic":
            events = list(self.stream_development_team(request))
            recorded = next((event for event in reversed(events) if event.get("type") == "meeting_recorded"), None)
            if not recorded:
                return {
                    "status": "blocked",
                    "reason": "Development-team planning produced no recorded build_plan.",
                    "events": events,
                    "fake_success": False,
                }
            build_prompt = (recorded.get("build_prompt") or "").strip()
            build_plan = recorded.get("build_plan") if isinstance(recorded.get("build_plan"), dict) else None
            slash_command = self._development_slash_command(agent_ids)
            effective_brief = build_prompt or topic
            slash_prompt = (
                f"{slash_command} {effective_brief}\n\n"
                "---\n"
                "Ontwikkelteam-protocol:\n"
                "- Werk binnen de Docker-isolated agent-sandbox; geen wijzigingen op de host buiten approval.\n"
                "- Codeer iteratief: kleinste werkbare diff, test, review.\n"
                "- Ondersteunende rollen communiceren via Gas Town MODE: nudge/mail/handoff; De Developper gebruikt het gekozen code-model.\n"
                f"- Stop na maximaal {max_iterations} pogingen zonder nieuwe testinformatie en vraag om verduidelijking.\n"
                "- Rapporteer welke files je raakt en welke tests je draait.\n"
                f"- Approval phrase blijft {APPROVAL_PHRASE}."
            )
            return {
                "status": "planned",
                "execution": "not_executed_by_ouroboros_chat_router",
                "approval_required": True,
                "approval_phrase": APPROVAL_PHRASE,
                "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
                "prompt": _clip_text(request.prompt, 3000),
                "augmented_prompt": _clip_text(topic, 6000),
                "clarifications_supplied": clarifications,
                "provider": recorded.get("provider") or provider,
                "model": recorded.get("model") or model,
                "recommended_models": {key: list(value) for key, value in CODING_MODEL_HINTS.items()},
                "personas": recorded.get("participants", []),
                "agent_ids": agent_ids[:12],
                "agent_command": slash_command,
                "slash_prompt": slash_prompt,
                "build_prompt": build_prompt,
                "build_plan": build_plan,
                "rounds": recorded.get("rounds", []),
                "summary": recorded.get("summary", ""),
                "meeting_id": recorded.get("meeting_id"),
                "meeting_type": recorded.get("meeting_type"),
                "planning_strategy": recorded.get("planning_strategy") or "deterministic",
                "next_route": "/api/cockpit/chat",
                "safety_note": (
                    "Het ontwikkelteam levert een werkbare bouwprompt. De uitvoering gebeurt in de "
                    "Cockpit agent-runtime achter de approval-gate, idealiter in een Docker-isolated job."
                ),
                "fake_success": False,
            }

        # Run the real four-persona meeting via the existing dev-team agenda.
        meeting_request = MeetingRequest(
            topic=topic,
            meeting_type="development_team",
            participants=persona_ids[:12],
            provider=provider,
            model=model,
            tools=[],
            allow_tools=False,
        )
        meeting_result = self.meetings.create_meeting(
            meeting_request,
            self.personas,
            llm_call=self._call_model_provider,
            knowledge_store=self.knowledge,
            web_context_fetcher=self._brave_knowledge_for_persona,
        )
        if meeting_result.get("status") == "blocked":
            return {**meeting_result, "next_route": "/api/cockpit/chat"}

        build_prompt = (meeting_result.get("build_prompt") or "").strip()
        build_plan = meeting_result.get("build_plan") if isinstance(meeting_result.get("build_plan"), dict) else None
        slash_command = self._development_slash_command(agent_ids)
        # Always produce a non-empty slash_prompt — fall back to the (augmented) topic so the
        # agent-runtime still has something concrete even when the meeting did not converge.
        effective_brief = build_prompt or topic
        slash_prompt = (
            f"{slash_command} {effective_brief}\n\n"
            "---\n"
            "Ontwikkelteam-protocol:\n"
            "- Werk binnen de Docker-isolated agent-sandbox; geen wijzigingen op de host buiten approval.\n"
            "- Codeer iteratief: kleinste werkbare diff, test, review.\n"
            f"- Stop na maximaal {max_iterations} pogingen zonder nieuwe testinformatie en vraag om verduidelijking.\n"
            "- Rapporteer welke files je raakt en welke tests je draait.\n"
            f"- Approval phrase blijft {APPROVAL_PHRASE}."
        )
        return {
            "status": "planned",
            "execution": "not_executed_by_ouroboros_chat_router",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
            "prompt": _clip_text(request.prompt, 3000),
            "augmented_prompt": _clip_text(topic, 6000),
            "clarifications_supplied": clarifications,
            "provider": meeting_result.get("provider") or provider,
            "model": meeting_result.get("model") or model,
            "recommended_models": {
                key: list(value)
                for key, value in CODING_MODEL_HINTS.items()
            },
            "personas": meeting_result.get("participants", []),
            "agent_ids": agent_ids[:12],
            "agent_command": slash_command,
            "slash_prompt": slash_prompt,
            "build_prompt": build_prompt,
            "build_plan": build_plan,
            "rounds": meeting_result.get("rounds", []),
            "summary": meeting_result.get("summary", ""),
            "meeting_id": meeting_result.get("meeting_id"),
            "meeting_type": meeting_result.get("meeting_type"),
            "next_route": "/api/cockpit/chat",
            "safety_note": (
                "Het ontwikkelteam levert een werkbare bouwprompt. De uitvoering gebeurt in de "
                "Cockpit agent-runtime achter de approval-gate, idealiter in een Docker-isolated job."
            ),
            "fake_success": False,
        }

    def _development_team_topic(self, request: DevelopmentTeamRequest) -> tuple[str, list[dict[str, str]]]:
        topic = _clip_text(request.prompt, 3000)
        clarifications = [
            item for item in (request.clarifications or [])
            if isinstance(item, dict) and str(item.get("answer") or "").strip()
        ]
        if clarifications:
            qa_lines = []
            for item in clarifications:
                question = _clip_text(str(item.get("question") or ""), 400)
                answer = _clip_text(str(item.get("answer") or ""), 1200)
                if question and answer:
                    qa_lines.append(f"- {question}\n  Antwoord: {answer}")
            if qa_lines:
                topic = f"{topic}\n\nVerduidelijking van de gebruiker:\n" + "\n".join(qa_lines)
        return topic, clarifications

    def stream_development_team_build(
        self, request: "DevelopmentTeamBuildRequest"
    ) -> "Iterator[dict[str, Any]]":
        """Orchestrate the isolated Development Team build-loop in a sandbox workspace."""
        from controller.dev_team_build import (
            DevTeamBuildSession,
            default_development_team_agents,
            format_build_plan,
            new_build_session_id,
            workspace_for,
        )

        build_plan = _build_plan_from_request(request)
        build_prompt = format_build_plan(build_plan)
        if _contains_secret_like({"build_plan": build_plan, "build_prompt": request.build_prompt}):
            raise ValueError(
                "Build-loop prompt appears to contain a secret, token, password, or bearer credential."
            )

        # Hard separation: the build runtime never reuses Meeting personas. The UI may
        # still send persona_ids for older clients, but they are intentionally ignored here.
        personas_by_role = default_development_team_agents()

        provider = str(request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        requested_model = str(request.model or "").strip()
        model_hints = CODING_MODEL_HINTS.get(provider, ())
        model = requested_model or (model_hints[0] if model_hints else DEFAULT_MODEL)
        session_id = new_build_session_id()
        builds_root = (self.data_dir / "dev-team-builds")
        builds_root.mkdir(parents=True, exist_ok=True)
        workspace = workspace_for(session_id, builds_root)
        workspace.mkdir(parents=True, exist_ok=True)

        session = DevTeamBuildSession(
            session_id=session_id,
            workspace=workspace,
            llm_call=self._call_model_provider,
            max_iterations=max(1, min(int(request.max_iterations or 4), 12)),
            min_iterations=max(1, min(int(request.min_iterations or 2), 12)),
            test_timeout=max(1.0, min(float(request.test_timeout_seconds or 120.0), 600.0)),
            llm_timeout_seconds=max(5.0, min(float(request.llm_timeout_seconds or 90.0), 600.0)),
        )

        try:
            for event in session.iterate(
                build_prompt=build_prompt,
                build_plan=build_plan,
                clarifications=request.clarifications,
                provider=provider,
                model=model,
                personas=personas_by_role,
            ):
                envelope = {"type": event.type, **event.data}
                envelope.setdefault("session_id", session_id)
                envelope.setdefault("timestamp", _now_iso())
                yield envelope
        except Exception as exc:  # noqa: BLE001
            yield {
                "type": "build_error",
                "session_id": session_id,
                "workspace_path": str(workspace),
                "error": str(exc),
                "timestamp": _now_iso(),
                "fake_success": False,
            }

    def chat(self, request: OuroborosChatRequest) -> dict[str, Any]:
        if _contains_secret_like({"prompt": request.prompt, "system_prompt": request.system_prompt, "history": request.history}):
            raise ValueError("Chat prompt/system/history content appears to contain a secret, token, password, or bearer credential.")
        slash_preview = self._slash_preview(request.prompt)
        if slash_preview:
            return slash_preview
        persona = self.personas.get(request.persona_id) or self.personas.get("ouroboros") or _default_persona()
        persona_id = str(persona.get("id") or "ouroboros")
        model_settings = persona.get("model_settings") if isinstance(persona.get("model_settings"), dict) else {}
        provider = (request.provider or model_settings.get("provider") or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        model = (request.model or model_settings.get("name") or persona.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

        attachment_payload = self._prepare_attachments([*request.files, *request.attachments], model=model)
        if attachment_payload["blocked"]:
            return {
                "status": "blocked",
                "reason": "image_model_unsupported",
                "provider": DEFAULT_PROVIDER,
                "model": model,
                "default_provider": DEFAULT_PROVIDER,
                "default_model": DEFAULT_MODEL,
                "response": (
                    "Ik heb de afbeelding(en) ontvangen, maar dit model is niet als vision-capable gedeclareerd. "
                    "Ik ga niet doen alsof ik de inhoud van de afbeelding begrijp."
                ),
                "attachments": attachment_payload["records"],
                "local_only": True,
                "fake_success": False,
            }
        conversation_id = request.conversation_id or request.thread_id
        recent_history = list(request.history or [])
        if not recent_history and conversation_id:
            try:
                recent_history = list(self.conversations.get(conversation_id).get("messages") or [])
            except KeyError:
                recent_history = []
        policy = enforce_tool_policy(persona)
        memories = self.memory.list(persona_id=persona_id, limit=16) if (persona.get("memory") or {}).get("enabled", True) else []
        knowledge = self.knowledge.snippets_for_persona(persona, request.prompt) if policy.get("can_search_files") else []
        web_knowledge = self._brave_knowledge_for_persona(persona, request.prompt) if policy.get("can_search_web") else []
        knowledge = [*web_knowledge, *knowledge]
        assembled = self.prompt_assembler.assemble(
            persona=persona,
            memories=memories,
            knowledge=knowledge,
            recent_history=recent_history,
            user_message=request.prompt,
            attachment_context=attachment_payload["context"],
        )
        system_prompt = "\n\n".join(part for part in [assembled["system_prompt"], request.system_prompt or ""] if str(part).strip())
        response = self._call_model_provider(
            prompt=assembled["user_prompt"],
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            history=_history_for_ollama(assembled["history"]),
            images=attachment_payload["images"],
        )
        status = "success" if response.get("ok") else "error"
        conversation = self.conversations.upsert_message(
            conversation_id=conversation_id,
            persona_id=persona_id,
            user_content=request.prompt,
            assistant_content=str(response.get("content", "")),
            title=request.prompt[:48],
        )
        return {
            "status": status,
            "provider": response.get("provider", provider),
            "model": model,
            "default_provider": DEFAULT_PROVIDER,
            "default_model": DEFAULT_MODEL,
            "persona_id": persona_id,
            "conversation": conversation,
            "response": response.get("content", ""),
            "error": response.get("error", ""),
            "sources": assembled.get("sources", []),
            "tool_policy": policy,
            "prompt_assembled": True,
            "approval_phrase": APPROVAL_PHRASE,
            "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
            "files_received": [_clip_text(path, 240) for path in request.files[:20]],
            "attachments": attachment_payload["records"],
            "transient_attachment_context": bool(attachment_payload["context"]),
            "network_call_made": bool(response.get("network_call_made")) or provider not in {DEFAULT_PROVIDER, "local", "ouroboros", "ollama"},
            "fake_success": False,
            "local_only": provider in {DEFAULT_PROVIDER, "local", "ouroboros", "ollama"} and not response.get("network_call_made"),
        }

    def cline_capabilities(self) -> dict[str, Any]:
        root = self.cline_root.expanduser().resolve()
        files: list[dict[str, Any]] = []
        detected: set[str] = set()
        for relative_path in ALLOWED_CLINE_FILES:
            try:
                path = _safe_relative_path(root, relative_path)
            except ValueError:
                continue
            record: dict[str, Any] = {
                "path": relative_path,
                "allowlisted": True,
                "exists": path.exists(),
                "read": False,
            }
            if path.exists() and path.is_file():
                try:
                    text = _read_text_limited(path)
                    record.update(
                        {
                            "read": True,
                            "size_bytes": path.stat().st_size,
                            "headings": _extract_headings(text),
                            "excerpt": _excerpt(text),
                        }
                    )
                    detected.add(relative_path)
                except OSError as exc:
                    record["error"] = str(exc)
            files.append(record)
        return {
            "status": "online" if root.exists() else "missing",
            "root": str(root),
            "read_only": True,
            "executed": False,
            "allowlisted_files": list(ALLOWED_CLINE_FILES),
            "files": files,
            "capabilities": self._cline_capability_cards(detected),
            "redaction": {"enabled": True, "secret_like_patterns": len(SECRET_PATTERNS)},
            "fake_success": False,
        }

    async def save_uploads(self, uploads: list[UploadFile]) -> dict[str, Any]:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        saved: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        for upload in uploads:
            original_name = Path(upload.filename or "upload").name
            safe_name = _safe_slug(original_name, fallback="upload")
            kind = _attachment_kind(original_name)
            content = await upload.read()
            if len(content) > MAX_UPLOAD_BYTES:
                saved.append({"filename": original_name, "status": "rejected", "reason": "file too large", "size": len(content)})
                continue
            if kind == "unsupported":
                saved.append({"filename": original_name, "status": "rejected", "reason": "unsupported file type", "size": len(content)})
                continue
            text = content.decode("utf-8", errors="ignore") if kind == "document" else ""
            if text and _contains_secret_like(text):
                saved.append({"filename": original_name, "status": "rejected", "reason": "secret-like content blocked", "size": len(content)})
                continue
            dest = (self.uploads_dir / f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe_name}").resolve()
            try:
                dest.relative_to(self.uploads_dir.resolve())
            except ValueError as exc:
                raise ValueError("Upload path escapes upload directory.") from exc
            dest.write_bytes(content)
            record = {
                "filename": original_name,
                "path": str(dest),
                "status": "ok",
                "size": len(content),
                "kind": kind,
                "mime_type": getattr(upload, "content_type", None),
            }
            saved.append(record)
            attachments.append({k: v for k, v in record.items() if k != "status"})
        return {
            "status": "success" if any(item["status"] == "ok" for item in saved) else "blocked",
            "uploaded": len([item for item in saved if item["status"] == "ok"]),
            "files": saved,
            "attachments": attachments,
            "storage": str(self.uploads_dir),
            "fake_success": False,
        }

    def _system_prompt(self, request: OuroborosChatRequest) -> str:
        persona = self.personas.get(request.persona_id) or self.personas.get("ouroboros") or _default_persona()
        pieces = [
            str(persona.get("system_prompt") or "").strip(),
            str(request.system_prompt or "").strip(),
            (
                "Core route guardrails: this endpoint does not execute shell, browser, Cline, or write tools. "
                f"When such action is needed, preserve the approval phrase {APPROVAL_PHRASE} and use the existing gated routes."
            ),
        ]
        return "\n\n".join(piece for piece in pieces if piece)

    def _slash_preview(self, prompt: str) -> dict[str, Any] | None:
        text = str(prompt or "").strip()
        if not text.startswith("/"):
            return None
        command = text[1:].partition(" ")[0].strip().lower() or "help"
        catalog = self.slash_menu()
        if command in {"agents", "help", "?"}:
            return {
                **catalog,
                "status": "online",
                "route": "slash_menu",
                "response": "Slash-menu beschikbaar; deze Ouroboros chat slice voert geen agent-commandos uit.",
            }
        return {
            "status": "blocked",
            "route": "slash_menu",
            "agent": command,
            "response": "Slash-agent execution stays with the existing approval-gated cockpit router.",
            "catalog": catalog,
            "approval_phrase": APPROVAL_PHRASE,
            "fake_success": False,
        }

    def slash_menu(self) -> dict[str, Any]:
        try:
            from controller.slash_agent_router import slash_command_catalog

            catalog = slash_command_catalog()
        except Exception as exc:
            catalog = {"status": "unavailable", "commands": {}, "reason": str(exc), "fake_success": False}
        commands = catalog.get("commands") if isinstance(catalog.get("commands"), dict) else {}
        cockpit_items = [
            {
                "command": key,
                "title": key.split(" ", 1)[0].lstrip("/") or key,
                "description": str(value),
                "source": "cockpit",
                "backend_route": "/api/cockpit/chat",
                "approval_required": any(agent in key for agent in ("/codex", "/deepseek", "/atlas", "/ruflo", "/claude", "/roo")),
                "enabled": True,
            }
            for key, value in commands.items()
        ]
        cline_items = [
            ("/plan", "Plan", "Cline-style plan mode for bounded task analysis.", False),
            ("/act", "Act", "Cline-style act mode routed through existing approval gates.", True),
            ("/deep-planning", "Deep Planning", "Use deeper task decomposition before action.", False),
            ("/newtask", "New Task", "Prepare a focused subtask handoff.", False),
            ("/persona", "Persona", "Create or select a GPT-like Ouroboros persona.", False),
            ("/meeting", "Meeting", "Let selected personas discuss a topic.", False),
            ("/read", "Read File", "Read-only file context pattern from Cline.", False),
            ("/list", "List Files", "Read-only file listing pattern from Cline.", False),
            ("/search", "Search Files", "Read-only search pattern from Cline.", False),
            ("/shell", "Shell", "Shell proposal requiring exact Akkoord through gated routes.", True),
            ("/patch", "Patch", "Write proposal requiring exact Akkoord through gated routes.", True),
            ("/browser", "Browser", "Browser action proposal requiring exact Akkoord.", True),
        ]
        items = [
            *cockpit_items,
            *[
                {
                    "command": command,
                    "title": title,
                    "description": description,
                    "source": "cline",
                    "backend_route": "/api/ouroboros-chat/chat",
                    "approval_required": approval_required,
                    "enabled": True,
                }
                for command, title, description, approval_required in cline_items
            ],
        ]
        catalog["approval_phrase"] = APPROVAL_PHRASE
        catalog["execution"] = "not_executed_by_ouroboros_chat_router"
        catalog["items"] = items
        catalog["cline_source_root"] = str(self.cline_root)
        catalog.setdefault("fake_success", False)
        return catalog

    def _development_slash_command(self, agent_ids: list[str]) -> str:
        preferred_order = ["codex", "roo", "claude", "deepseek", "atlas", "ruflo", "agents"]
        selected = [str(item or "").strip().lower().lstrip("/") for item in agent_ids if str(item or "").strip()]
        for agent in [*selected, *preferred_order]:
            if agent in preferred_order:
                return f"/{agent}"
        return "/codex"

    def _prepare_attachments(self, attachments: list[Any], *, model: str) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        context_parts: list[str] = []
        images: list[str] = []
        blocked = False
        supports_images = _model_supports_images(model)

        for item in attachments[:20]:
            path = _safe_attachment_path(item)
            if path is None:
                continue
            kind = _attachment_kind(path.name)
            record = {
                "path": str(path),
                "filename": path.name,
                "kind": kind,
                "exists": path.exists(),
                "included": False,
            }
            if not path.exists() or not path.is_file():
                record["reason"] = "not_found"
                records.append(record)
                continue
            if kind == "image":
                if not supports_images:
                    record["reason"] = "image_model_unsupported"
                    blocked = True
                else:
                    images.append(base64.b64encode(path.read_bytes()).decode("ascii"))
                    record["included"] = True
                records.append(record)
                continue
            if kind == "document":
                text = _extract_attachment_text(path)
                if text.strip():
                    context_parts.append(f"--- {path.name} ---\n{text[:MAX_ATTACHMENT_CONTEXT_CHARS]}")
                    record["included"] = True
                else:
                    record["reason"] = "empty_or_unreadable"
                records.append(record)
                continue
            record["reason"] = "unsupported_file_type"
            records.append(record)

        return {
            "blocked": blocked,
            "records": records,
            "context": "\n\n".join(context_parts)[:MAX_ATTACHMENT_CONTEXT_CHARS],
            "images": images,
        }

    def model_options(self) -> dict[str, Any]:
        key_status: dict[str, Any] = {}
        subscription_statuses: dict[str, Any] = {}
        openai_models = list(OPENAI_MODEL_OPTIONS)
        try:
            from controller.api_key_store import provider_key_status

            key_status = provider_key_status()
        except Exception:
            key_status = {}
        try:
            from controller.subscription_store import subscription_status

            subscription_statuses = subscription_status()
        except Exception:
            subscription_statuses = {}
        try:
            from controller.openai_model_catalog import openai_api_model_choices

            openai_models = list(openai_api_model_choices()) or openai_models
        except Exception:
            pass

        provider_models = {
            **PROVIDER_MODEL_OPTIONS,
            "openai": {**PROVIDER_MODEL_OPTIONS["openai"], "models": openai_models, "default_model": openai_models[0] if openai_models else "gpt-5.4-mini"},
        }
        providers: list[dict[str, Any]] = [
            {
                "id": "ollama",
                "label": "Ollama local",
                "models": self._local_ollama_models(),
                "default_model": DEFAULT_MODEL,
                "configured": True,
                "local_only": True,
                "key_source": "local",
                "direct_chat": True,
            }
        ]
        chatgpt_codex = _chatgpt_codex_status(
            subscription_statuses.get("openai") if isinstance(subscription_statuses.get("openai"), dict) else {}
        )
        providers.append(
            {
                "id": CHATGPT_CODEX_PROVIDER,
                "label": "ChatGPT-Codex abonnement",
                "models": list(CHATGPT_CODEX_MODEL_OPTIONS),
                "default_model": CHATGPT_CODEX_DEFAULT_MODEL,
                "configured": chatgpt_codex["configured"],
                "direct_chat": chatgpt_codex["direct_chat"],
                "key_source": chatgpt_codex["key_source"],
                "auth_mode": chatgpt_codex["auth_mode"],
                "subscription_status": chatgpt_codex["status"],
                "token_file_present": chatgpt_codex["token_file_present"],
                "token_file": chatgpt_codex["token_file"],
                "token_sources": chatgpt_codex["token_sources"],
                "login_command": "goose configure chatgpt_codex, codex login, or cd /home/pwintri2/chatgpt-copilot && npx ts-node scripts/chatgpt-oauth.ts",
                "local_only": False,
            }
        )
        for provider_id, config in provider_models.items():
            key = key_status.get(provider_id) if isinstance(key_status.get(provider_id), dict) else {}
            sub = subscription_statuses.get(provider_id) if isinstance(subscription_statuses.get(provider_id), dict) else {}
            key_configured = bool(key.get("configured"))
            subscription_has_credential = bool(sub.get("active") and sub.get("has_credential") and not sub.get("expired"))
            api_key_ready = bool(sub.get("api_key_ready"))
            models = _dedupe_strings(config.get("models", []), fallback=tuple(sub.get("models", []) if isinstance(sub.get("models"), list) else ()))
            providers.append(
                {
                    "id": provider_id,
                    "label": config.get("label", provider_id),
                    "models": models,
                    "default_model": config.get("default_model") or (models[0] if models else ""),
                    "configured": bool(key_configured or subscription_has_credential),
                    "direct_chat": bool(key_configured or api_key_ready),
                    "key_source": key.get("source") if key_configured else (f"subscription:{sub.get('auth_mode')}" if subscription_has_credential else "missing"),
                    "auth_mode": sub.get("auth_mode", ""),
                    "subscription_status": sub.get("status", "inactive") if sub else "inactive",
                    "api_key_ready": api_key_ready or key_configured,
                    "local_only": False,
                }
            )

        try:
            from controller.roo_cli_runtime import ROO_OAUTH_MODEL, ROO_OAUTH_PROVIDER, roo_cli_status, roo_cloud_models

            roo_status = roo_cli_status()
            cloud = roo_cloud_models(timeout_seconds=2, max_models=120) if roo_status.get("available") else {}
            roo_models = _dedupe_strings(cloud.get("models", []) if isinstance(cloud.get("models"), list) else [], fallback=(ROO_OAUTH_MODEL,))
            providers.append(
                {
                    "id": ROO_OAUTH_PROVIDER,
                    "label": "Roo Cloud OAuth",
                    "models": roo_models,
                    "default_model": ROO_OAUTH_MODEL,
                    "configured": bool(roo_status.get("oauth_logged_in") or roo_status.get("auth", {}).get("ok")),
                    "direct_chat": False,
                    "key_source": "roo_oauth",
                    "auth_mode": "oauth",
                    "subscription_status": str(roo_status.get("status") or "unknown"),
                    "agent_runtime_only": True,
                    "local_only": False,
                }
            )
        except Exception:
            pass

        brave = key_status.get("brave") if isinstance(key_status.get("brave"), dict) else {}
        return {
            "status": "online",
            "providers": providers,
            "brave": {
                "configured": bool(brave.get("configured")),
                "key_source": brave.get("source", "missing"),
                "used_for_persona_web_search": True,
            },
            "fake_success": False,
        }

    def _local_ollama_models(self) -> list[str]:
        models: list[Any] = []
        if self.ollama_client is not None and callable(getattr(self.ollama_client, "list_models", None)):
            try:
                models = list(self.ollama_client.list_models())
            except Exception:
                models = []
        if not models:
            try:
                import requests

                base_url = (os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
                if base_url.endswith("/api"):
                    base_url = base_url[:-4]
                response = requests.get(f"{base_url}/api/tags", timeout=2.0)
                response.raise_for_status()
                models = [item.get("name") for item in response.json().get("models", []) if isinstance(item, dict)]
            except Exception:
                models = []
        return _dedupe_strings(models, fallback=LOCAL_OLLAMA_FALLBACK_MODELS)

    def _cockpit_provider_api_keys(self) -> dict[str, str]:
        keys: dict[str, str] = {}
        try:
            from controller.api_key_store import load_provider_api_keys

            keys.update(load_provider_api_keys())
        except Exception:
            pass
        try:
            from controller.subscription_store import subscription_api_key_for_provider

            for provider_id in PROVIDER_MODEL_OPTIONS:
                if keys.get(provider_id):
                    continue
                value = subscription_api_key_for_provider(provider_id)
                if value:
                    keys[provider_id] = value
        except Exception:
            pass
        return keys

    def _brave_knowledge_for_persona(self, persona: dict[str, Any], query: str) -> list[dict[str, Any]]:
        clean_query = _clip_text(query, 400)
        if not clean_query:
            return []
        try:
            from controller.brave_search import search_brave_llm_context

            result = search_brave_llm_context(clean_query, maximum_number_of_urls=5)
        except Exception as exc:
            return [
                {
                    "label": "Brave Search",
                    "source": "brave:error",
                    "snippet": f"Brave Search context kon niet worden opgehaald: {exc}",
                    "score": 1,
                }
            ]
        if result.get("status") != "success":
            reason = result.get("reason") or result.get("status") or "unavailable"
            return [
                {
                    "label": "Brave Search",
                    "source": "brave:status",
                    "snippet": f"Brave Search is niet beschikbaar voor deze beurt: {reason}.",
                    "score": 1,
                }
            ]
        document = str(result.get("document") or "").strip()
        if not document:
            return []
        return [
            {
                "label": "Brave Search",
                "source": "brave:llm_context",
                "snippet": document[:4000],
                "score": 5,
                "source_urls": result.get("source_urls") or [],
                "taint": "untrusted_web",
            }
        ]

    def _chatgpt_codex_runtime_token(self) -> tuple[dict[str, Any] | None, str]:
        refresh_errors: list[str] = []
        for source in _chatgpt_codex_token_sources():
            token = source.get("token", {}) if isinstance(source.get("token"), dict) else {}
            if not token:
                continue
            if _token_has_time_left(token) and _chatgpt_token_access(token):
                return token, str(source.get("id") or "oauth_shared_file")
            if _chatgpt_token_refresh(token):
                save_token = source.get("save") if callable(source.get("save")) else None
                try:
                    return (
                        self._refresh_chatgpt_codex_token(token, persist=bool(save_token), save_token=save_token),
                        str(source.get("id") or "oauth_shared_file"),
                    )
                except ValueError as exc:
                    refresh_errors.append(f"{source.get('id')}: {_redact_secret_like(str(exc))}")

        try:
            from controller.subscription_store import subscription_credential_for_provider

            credential = subscription_credential_for_provider("openai")
        except Exception:
            credential = {}
        if credential.get("usable") and credential.get("auth_mode") == "oauth_refresh_token":
            refreshed = self._refresh_chatgpt_codex_token(
                {"provider": "chatgpt", "refreshToken": credential.get("refresh_token")},
                persist=False,
            )
            return refreshed, "subscription:oauth_refresh_token"
        if refresh_errors:
            raise ValueError("ChatGPT-Codex OAuth refresh failed for known token stores: " + "; ".join(refresh_errors))
        return None, "missing"

    def _refresh_chatgpt_codex_token(
        self,
        token: dict[str, Any],
        *,
        persist: bool,
        save_token: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        refresh_token = _chatgpt_token_refresh(token)
        if not refresh_token:
            raise ValueError("ChatGPT-Codex OAuth refresh token is missing.")
        try:
            response = _http_post(
                CHATGPT_CODEX_TOKEN_ENDPOINT,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": CHATGPT_CODEX_CLIENT_ID,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
        except Exception as exc:
            raise ValueError(f"ChatGPT-Codex token refresh failed: {_redact_secret_like(str(exc))}") from exc
        if not response.ok:
            raise ValueError(f"ChatGPT-Codex token refresh failed: {_redact_secret_like(response.text[:240])}")
        data = response.json()
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("ChatGPT-Codex token refresh returned no access token.")
        refreshed = {
            **token,
            "provider": "chatgpt",
            "accessToken": access_token,
            "refreshToken": str(data.get("refresh_token") or refresh_token),
            "expiresAt": int((time.time() + int(data.get("expires_in") or 3600)) * 1000),
        }
        id_token = str(data.get("id_token") or "").strip()
        if id_token:
            refreshed["idToken"] = id_token
        if persist:
            if save_token is not None:
                save_token(refreshed)
            else:
                _save_chatgpt_copilot_token(refreshed)
        return refreshed

    def _call_chatgpt_codex(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        try:
            token, source = self._chatgpt_codex_runtime_token()
        except ValueError as exc:
            return {"ok": False, "content": "", "error": str(exc), "provider": CHATGPT_CODEX_PROVIDER, "model": model}
        if not token:
            return {
                "ok": False,
                "content": "",
                "error": (
                    "ChatGPT-Codex OAuth is not linked. Link Goose ChatGPT-Codex, run codex login, run the "
                    "chatgpt-copilot OAuth login, or configure an OpenAI oauth_refresh_token subscription."
                ),
                "provider": CHATGPT_CODEX_PROVIDER,
                "model": model,
            }
        access_token = _chatgpt_token_access(token)
        account_id = _chatgpt_token_account_id(token)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "originator": "codex_cli_rs",
            "OpenAI-Beta": "responses=experimental",
        }
        if account_id:
            headers["chatgpt-account-id"] = account_id

        input_items: list[dict[str, Any]] = []
        if system_prompt.strip():
            input_items.append(
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": _clip_text(system_prompt, MAX_TEXT_CHARS)}],
                }
            )
        for item in history[-20:]:
            role = "assistant" if item.get("role") == "assistant" else "user"
            content = _clip_text(item.get("content", ""), MAX_TEXT_CHARS)
            if not content:
                continue
            input_items.append(
                {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "output_text" if role == "assistant" else "input_text", "text": content}],
                }
            )
        input_items.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": _clip_text(prompt, MAX_TEXT_CHARS)}],
            }
        )
        body = {
            "model": model or CHATGPT_CODEX_DEFAULT_MODEL,
            "input": input_items,
            "instructions": CHATGPT_CODEX_INSTRUCTIONS,
            "store": False,
            "stream": False,
            "include": ["reasoning.encrypted_content"],
            "text": {"verbosity": "medium"},
        }
        try:
            response = _http_post(
                f"{CHATGPT_CODEX_BASE_URL}/codex/responses",
                headers=headers,
                json_body=body,
                timeout=max(10.0, self.ollama_timeout_seconds),
            )
        except Exception as exc:
            return {
                "ok": False,
                "content": "",
                "error": f"ChatGPT-Codex request failed: {_redact_secret_like(str(exc))}",
                "provider": CHATGPT_CODEX_PROVIDER,
                "model": model,
                "network_call_made": True,
            }
        if not response.ok:
            return {
                "ok": False,
                "content": "",
                "error": f"ChatGPT-Codex API error {response.status_code}: {_redact_secret_like(response.text[:500])}",
                "provider": CHATGPT_CODEX_PROVIDER,
                "model": model,
                "network_call_made": True,
                "auth_source": source,
            }
        try:
            data = response.json()
        except Exception as exc:
            return {
                "ok": False,
                "content": "",
                "error": f"ChatGPT-Codex returned invalid JSON: {exc}",
                "provider": CHATGPT_CODEX_PROVIDER,
                "model": model,
                "network_call_made": True,
                "auth_source": source,
            }
        content = self._extract_chatgpt_codex_text(data).strip()
        return {
            "ok": bool(content),
            "content": content,
            "error": "" if content else "ChatGPT-Codex returned no response text.",
            "provider": CHATGPT_CODEX_PROVIDER,
            "model": model,
            "raw_status": "success" if content else "empty",
            "network_call_made": True,
            "auth_source": source,
        }

    def _extract_chatgpt_codex_text(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, list):
            return "\n".join(part for part in (self._extract_chatgpt_codex_text(item) for item in payload) if part)
        if not isinstance(payload, dict):
            return ""
        for key in ("output_text", "response", "content", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if isinstance(item, dict):
                    content = item.get("content")
                    if isinstance(content, list):
                        parts.extend(self._extract_chatgpt_codex_text(part) for part in content)
                    else:
                        parts.append(self._extract_chatgpt_codex_text(item))
            return "\n".join(part for part in parts if part)
        choices = payload.get("choices")
        if isinstance(choices, list):
            parts = []
            for choice in choices:
                if isinstance(choice, dict):
                    message = choice.get("message")
                    parts.append(self._extract_chatgpt_codex_text(message if message is not None else choice))
            return "\n".join(part for part in parts if part)
        return ""

    def _call_model_provider(
        self,
        *,
        prompt: str,
        provider: str,
        model: str,
        system_prompt: str,
        history: list[dict[str, str]],
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        provider_id = str(provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        if provider_id in CHATGPT_CODEX_ALIASES:
            return self._call_chatgpt_codex(
                prompt=prompt,
                model=model or CHATGPT_CODEX_DEFAULT_MODEL,
                system_prompt=system_prompt,
                history=history,
            )
        if provider_id in {DEFAULT_PROVIDER, "local", "ouroboros", "ollama"}:
            result = self._call_ollama(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                history=history,
                images=images,
            )
            return {**result, "provider": DEFAULT_PROVIDER, "model": model}
        try:
            from controller.multi_api_router import MultiAPIRouter

            router = MultiAPIRouter(api_keys=self._cockpit_provider_api_keys())
            routed = asyncio.run(
                router.route_chat(
                    provider=provider_id,
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history=history,
                )
            )
        except Exception as exc:
            return {"ok": False, "content": "", "error": str(exc), "provider": provider_id, "model": model}
        content = str(routed.get("response") or routed.get("content") or "").strip()
        ok = routed.get("status") == "success" and bool(content)
        error = str(routed.get("error") or routed.get("reason") or routed.get("message") or "")
        return {
            "ok": ok,
            "content": content,
            "error": "" if ok else error or f"{provider_id} returned no response.",
            "provider": routed.get("provider", provider_id),
            "model": routed.get("model", model),
            "raw_status": routed.get("status"),
            "network_call_made": routed.get("network_call_made", False),
        }

    def _call_ollama(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str,
        history: list[dict[str, str]],
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.ollama_client is not None and callable(getattr(self.ollama_client, "chat", None)):
            try:
                content = self.ollama_client.chat(
                    user_input=prompt,
                    history=history,
                    model=model,
                    system_prompt=system_prompt,
                    images=images or None,
                )
            except TypeError:
                content = self.ollama_client.chat(prompt, history=history, model=model, system_prompt=system_prompt)
            except Exception as exc:
                return {"ok": False, "content": "", "error": str(exc)}
            return {"ok": True, "content": str(content or ""), "error": ""}

        try:
            import requests

            base_url = (os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
            if base_url.endswith("/api"):
                base_url = base_url[:-4]
            user_message: dict[str, Any] = {"role": "user", "content": prompt}
            if images:
                user_message["images"] = images
            messages = [{"role": "system", "content": system_prompt}, *history, user_message]
            response = requests.post(
                f"{base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.15}},
                timeout=max(1.0, self.ollama_timeout_seconds),
            )
            response.raise_for_status()
            return {"ok": True, "content": str(response.json().get("message", {}).get("content", "") or ""), "error": ""}
        except Exception as exc:
            return {"ok": False, "content": "", "error": f"Local Ollama chat failed for {model}: {exc}"}

    def _cline_capability_cards(self, detected: set[str]) -> list[dict[str, Any]]:
        def has(path: str) -> bool:
            return path in detected

        return [
            {
                "id": "plan_act",
                "label": "Plan and Act workflow",
                "detected": has("docs/core-workflows/plan-and-act.mdx"),
                "source": "docs/core-workflows/plan-and-act.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "task_management",
                "label": "Task management patterns",
                "detected": has("docs/core-workflows/task-management.mdx"),
                "source": "docs/core-workflows/task-management.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "checkpoints",
                "label": "Checkpoint and restore concepts",
                "detected": has("docs/core-workflows/checkpoints.mdx"),
                "source": "docs/core-workflows/checkpoints.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "cline_rules",
                "label": "Cline rules and customization",
                "detected": has("docs/customization/cline-rules.mdx"),
                "source": "docs/customization/cline-rules.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "subagents",
                "label": "Subagent planning context",
                "detected": has("docs/features/subagents.mdx"),
                "source": "docs/features/subagents.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "mcp",
                "label": "MCP integration concepts",
                "detected": has("docs/mcp/mcp-overview.mdx"),
                "source": "docs/mcp/mcp-overview.mdx",
                "execution": "read_only_context",
            },
        ]


ouroboros_chat_router = APIRouter(prefix="/api/ouroboros-chat", tags=["ouroboros-chat"])


def _service_from_request(request: Request) -> OuroborosChatService:
    service = getattr(request.app.state, "ouroboros_chat_service", None)
    if service is None:
        service = OuroborosChatService(ollama_timeout_seconds=600.0)
        request.app.state.ouroboros_chat_service = service
    return service


@ouroboros_chat_router.post("/chat")
async def chat(request_body: OuroborosChatRequest, request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_service_from_request(request).chat, request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if _MULTIPART_AVAILABLE and FastAPIFile is not None:

    @ouroboros_chat_router.post("/upload")
    async def upload_files(request: Request, files: list[UploadFile] = FastAPIFile(...)) -> dict[str, Any]:
        try:
            return await _service_from_request(request).save_uploads(files)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

else:

    @ouroboros_chat_router.post("/upload")
    async def upload_files_unavailable() -> dict[str, Any]:
        raise HTTPException(status_code=503, detail="python-multipart is not installed in this runtime.")


@ouroboros_chat_router.get("/cline-capabilities")
async def cline_capabilities(request: Request) -> dict[str, Any]:
    return _service_from_request(request).cline_capabilities()


@ouroboros_chat_router.get("/slash-menu")
async def slash_menu(request: Request) -> dict[str, Any]:
    return _service_from_request(request).slash_menu()


@ouroboros_chat_router.get("/uploads/{filename}")
async def get_upload(filename: str, request: Request) -> Any:
    if FileResponse is None:
        raise HTTPException(status_code=503, detail="File responses are not available in this runtime.")
    service = _service_from_request(request)
    safe_name = Path(filename or "").name
    path = (service.uploads_dir / safe_name).resolve()
    try:
        path.relative_to(service.uploads_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="upload path escapes upload directory") from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"unknown upload: {safe_name}")
    return FileResponse(path)


@ouroboros_chat_router.get("/personas")
async def list_personas(request: Request, include_development_team: bool = False) -> dict[str, Any]:
    service = _service_from_request(request)
    personas = service.personas.list_personas()
    if not include_development_team:
        personas = [
            persona for persona in personas
            if str(persona.get("id") or "") not in HIDDEN_DEVELOPMENT_PERSONA_IDS
        ]
    return {
        "status": "online",
        "path": str(service.personas.path),
        "personas": personas,
        "count": len(personas),
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }


@ouroboros_chat_router.post("/personas")
async def upsert_persona(request_body: PersonaRequest, request: Request) -> dict[str, Any]:
    try:
        persona = _service_from_request(request).personas.upsert(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "saved", "persona": persona, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.post("/personas/import")
async def import_persona(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        persona = _service_from_request(request).personas.import_persona(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "imported", "persona": persona, "fake_success": False}


@ouroboros_chat_router.get("/personas/{persona_id}")
async def get_persona(persona_id: str, request: Request) -> dict[str, Any]:
    persona = _service_from_request(request).personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    return {"status": "online", "persona": persona, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.get("/personas/{persona_id}/export")
async def export_persona(persona_id: str, request: Request) -> dict[str, Any]:
    persona = _service_from_request(request).personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    return {"status": "exported", "persona": persona, "schema": "ouroboros_chat_persona_v1", "fake_success": False}


@ouroboros_chat_router.post("/personas/{persona_id}/duplicate")
async def duplicate_persona(persona_id: str, request: Request) -> dict[str, Any]:
    try:
        persona = _service_from_request(request).personas.duplicate(persona_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from exc
    return {"status": "duplicated", "persona": persona, "fake_success": False}


@ouroboros_chat_router.put("/personas/{persona_id}")
async def update_persona(persona_id: str, request_body: PersonaRequest, request: Request) -> dict[str, Any]:
    update = _model_to_dict(request_body)
    update["id"] = persona_id
    try:
        persona = _service_from_request(request).personas.upsert(PersonaRequest(**update))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "saved", "persona": persona, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.put("/personas/{persona_id}/tools")
async def update_persona_tools(persona_id: str, payload: dict[str, bool], request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    try:
        persona = service.personas.patch(persona_id, {"tools": payload})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "saved", "persona": persona, "tool_policy": enforce_tool_policy(persona), "fake_success": False}


@ouroboros_chat_router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str, request: Request, hard: bool = False) -> dict[str, Any]:
    try:
        result = _service_from_request(request).personas.archive(persona_id, hard=hard)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from exc
    return {**result, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.get("/tools")
async def get_tools() -> dict[str, Any]:
    return tool_catalog()


@ouroboros_chat_router.get("/model-options")
async def get_model_options(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(_service_from_request(request).model_options)


@ouroboros_chat_router.get("/conversations")
async def list_conversations(request: Request, persona_id: str = "", limit: int = 100) -> dict[str, Any]:
    service = _service_from_request(request)
    conversations = service.conversations.list(persona_id=persona_id or None, limit=max(1, min(limit, 500)))
    return {"status": "online", "conversations": conversations, "count": len(conversations), "fake_success": False}


@ouroboros_chat_router.post("/conversations")
async def create_conversation(request_body: ConversationRequest, request: Request) -> dict[str, Any]:
    conversation = _service_from_request(request).conversations.create(
        persona_id=request_body.persona_id,
        title=request_body.title,
    )
    return {"status": "created", "conversation": conversation, "fake_success": False}


@ouroboros_chat_router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    try:
        conversation = _service_from_request(request).conversations.get(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown conversation: {conversation_id}") from exc
    return {"status": "online", "conversation": conversation, "fake_success": False}


@ouroboros_chat_router.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        conversation = _service_from_request(request).conversations.update(conversation_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown conversation: {conversation_id}") from exc
    return {"status": "saved", "conversation": conversation, "fake_success": False}


@ouroboros_chat_router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request, hard: bool = False) -> dict[str, Any]:
    try:
        return {**_service_from_request(request).conversations.delete(conversation_id, hard=hard), "fake_success": False}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown conversation: {conversation_id}") from exc


@ouroboros_chat_router.get("/memory")
async def list_memory(request: Request, persona_id: str = "", scope: str = "", limit: int = 100) -> dict[str, Any]:
    service = _service_from_request(request)
    items = service.memory.list(persona_id=persona_id or None, scope=scope or None, limit=max(1, min(limit, 500)))
    return {"status": "online", "memory": items, "count": len(items), "fake_success": False}


@ouroboros_chat_router.post("/memory")
async def create_memory(request_body: MemoryRequest, request: Request) -> dict[str, Any]:
    try:
        item = _service_from_request(request).memory.create(_model_to_dict(request_body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "created", "memory": item, "fake_success": False}


@ouroboros_chat_router.put("/memory/{memory_id}")
async def update_memory(memory_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        item = _service_from_request(request).memory.update(memory_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown memory: {memory_id}") from exc
    return {"status": "saved", "memory": item, "fake_success": False}


@ouroboros_chat_router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> dict[str, Any]:
    try:
        return {**_service_from_request(request).memory.delete(memory_id), "fake_success": False}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown memory: {memory_id}") from exc


@ouroboros_chat_router.get("/knowledge/search")
async def search_knowledge(request: Request, persona_id: str, q: str = "", limit: int = 5) -> dict[str, Any]:
    service = _service_from_request(request)
    persona = service.personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    snippets = service.knowledge.snippets_for_persona(persona, q, limit=max(1, min(limit, 20)))
    return {"status": "online", "snippets": snippets, "count": len(snippets), "fake_success": False}


@ouroboros_chat_router.post("/development-team/intake")
async def plan_development_team_intake(request_body: DevelopmentTeamIntakeRequest, request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    try:
        return await asyncio.to_thread(service.development_team_intake, request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ouroboros_chat_router.post("/development-team")
async def plan_development_team(request_body: DevelopmentTeamRequest, request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    try:
        return await asyncio.to_thread(service.development_team, request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ouroboros_chat_router.get("/development-team/agents")
async def list_development_team_agents() -> dict[str, Any]:
    agents = _public_development_team_agents()
    return {"status": "online", "agents": agents, "count": len(agents), "fake_success": False}


@ouroboros_chat_router.post("/development-team/stream")
async def stream_development_team(request_body: DevelopmentTeamRequest, request: Request) -> Any:
    """SSE stream: isolated five-role Development Team planning, separate from Meeting personas."""
    try:
        from fastapi.responses import StreamingResponse
    except Exception as exc:  # pragma: no cover - fastapi shim path
        raise HTTPException(status_code=500, detail=f"StreamingResponse not available: {exc}") from exc
    service = _service_from_request(request)
    try:
        iterator = service.stream_development_team(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream() -> "AsyncIterator[bytes]":
        loop = asyncio.get_event_loop()

        def _next(it: "Iterator[dict[str, Any]]") -> dict[str, Any] | None:
            try:
                return next(it)
            except StopIteration:
                return None
            except Exception as exc:  # noqa: BLE001
                return {
                    "type": "meeting_error",
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "timestamp": _now_iso(),
                    "fake_success": False,
                }

        while True:
            future = loop.run_in_executor(None, _next, iterator)
            while True:
                try:
                    event = await asyncio.wait_for(asyncio.shield(future), timeout=5.0)
                    break
                except asyncio.TimeoutError:
                    yield b": ping\n\n"

            if event is None:
                break
            event_name = str(event.get("type") or "meeting_event").replace("\n", " ")
            payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
            chunk = f"event: {event_name}\ndata: {payload}\n\n"
            yield chunk.encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@ouroboros_chat_router.post("/development-team/build")
async def stream_development_team_build(
    request_body: DevelopmentTeamBuildRequest, request: Request
) -> Any:
    """SSE stream: dev-team agents bouwen zelf in een sandbox tot tests groen zijn."""
    try:
        from fastapi.responses import StreamingResponse
    except Exception as exc:  # pragma: no cover - fastapi shim path
        raise HTTPException(status_code=500, detail=f"StreamingResponse not available: {exc}") from exc
    service = _service_from_request(request)
    try:
        iterator = service.stream_development_team_build(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream() -> "AsyncIterator[bytes]":
        loop = asyncio.get_event_loop()

        def _next(it: "Iterator[dict[str, Any]]") -> dict[str, Any] | None:
            try:
                return next(it)
            except StopIteration:
                return None
            except Exception as exc:  # noqa: BLE001
                return {
                    "type": "build_error",
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "timestamp": _now_iso(),
                    "fake_success": False,
                }

        while True:
            future = loop.run_in_executor(None, _next, iterator)
            while True:
                try:
                    event = await asyncio.wait_for(asyncio.shield(future), timeout=5.0)
                    break
                except asyncio.TimeoutError:
                    yield b"".join(b": ping\n" for _ in range(500)) + b"\n"

            if event is None:
                break
            event_name = str(event.get("type") or "build_event").replace("\n", " ")
            payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
            chunk = f"event: {event_name}\ndata: {payload}\n\n"
            yield chunk.encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@ouroboros_chat_router.get("/meetings")
async def list_meetings(request: Request, limit: int = 50) -> dict[str, Any]:
    service = _service_from_request(request)
    records = service.meetings.list_meetings(limit=max(1, min(int(limit), 200)))
    return {
        "status": "online",
        "directory": str(service.meetings.directory),
        "meetings": records,
        "count": len(records),
        "tool_policy": service.meetings.tool_policy(),
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }


@ouroboros_chat_router.post("/meetings")
async def create_meeting(request_body: MeetingRequest, request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    try:
        return await asyncio.to_thread(service.create_meeting, request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ouroboros_chat_router.post("/meetings/stream")
async def stream_meeting(request_body: MeetingRequest, request: Request) -> Any:
    try:
        from fastapi.responses import StreamingResponse
    except Exception as exc:  # pragma: no cover - fastapi shim path
        raise HTTPException(status_code=500, detail=f"StreamingResponse not available: {exc}") from exc
    service = _service_from_request(request)
    try:
        iterator = service.stream_meeting(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream() -> "AsyncIterator[bytes]":
        loop = asyncio.get_event_loop()

        def _next(it: "Iterator[dict[str, Any]]") -> dict[str, Any] | None:
            try:
                return next(it)
            except StopIteration:
                return None
            except Exception as exc:  # noqa: BLE001
                return {
                    "type": "meeting_error",
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "timestamp": _now_iso(),
                    "fake_success": False,
                }

        while True:
            future = loop.run_in_executor(None, _next, iterator)
            while True:
                try:
                    event = await asyncio.wait_for(asyncio.shield(future), timeout=5.0)
                    break
                except asyncio.TimeoutError:
                    yield b"".join(b": ping\n" for _ in range(500)) + b"\n"

            if event is None:
                break
            event_name = str(event.get("type") or "meeting_event").replace("\n", " ")
            payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
            chunk = f"event: {event_name}\ndata: {payload}\n\n"
            yield chunk.encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@ouroboros_chat_router.put("/meetings/{meeting_id}")
async def save_meeting_snapshot(meeting_id: str, request_body: MeetingSaveRequest, request: Request) -> dict[str, Any]:
    try:
        return _service_from_request(request).meetings.save_snapshot(meeting_id, request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ouroboros_chat_router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, request: Request) -> dict[str, Any]:
    try:
        return _service_from_request(request).meetings.read_meeting(meeting_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown meeting: {meeting_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = [
    "APPROVAL_PHRASE",
    "ALLOWED_CLINE_FILES",
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "DEV_TEAM_DEFAULT_PERSONA_IDS",
    "DevelopmentTeamBuildRequest",
    "DevelopmentTeamIntakeRequest",
    "DevelopmentTeamRequest",
    "MeetingRequest",
    "MeetingSaveRequest",
    "OuroborosChatRequest",
    "OuroborosChatService",
    "PersonaRequest",
    "init_ouroboros_chat_routes",
    "ouroboros_chat_router",
]
