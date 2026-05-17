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
from typing import Any, Callable, Mapping
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
from controller.openclaw_voice import openclaw_voice_status_payload
from controller.ziel_policy import ziel_guardrail_note


REGISTERED_TOOLS: tuple[str, ...] = (
    "memory_search",
    "agentic_ecosystem_context",
    "browser_research",
    "brave_search",
    "ns_travel_advice",
    "ov9292_travel_advice",
    "connector_intent_preview",
    "gmail_status",
    "gmail_search",
    "google_drive_status",
    "google_drive_list",
    "microsoft_graph_status",
    "teams_list",
    "onedrive_list",
    "outlook_read",
    "sharepoint_status",
    "sharepoint_sites",
    "sharepoint_libraries",
    "github_status",
    "github_repo",
    "github_search_repositories",
    "vps_status",
    "vps_login_check",
    "vps_sync_preview",
    "vps_sync_execute",
    "vps_ui_sync_preview",
    "vps_ui_sync_execute",
    "chroma_sync_status",
    "chroma_sync_preview",
    "chroma_sync_execute",
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
        "Gebruikt de officiële NS Reisplanner als browser/zichtbare-bron route voor Nederlandse treinvragen. Read-only; geen Akkoord nodig. Exacte tijden worden alleen genoemd als ze zichtbaar uit de officiële plannerpagina of expliciet opt-in NS API komen.",
        {
            "from_station": {"type": "string", "description": "Vertrekstation, naam of NS-code."},
            "to_station": {"type": "string", "description": "Aankomststation, naam of NS-code."},
            "date": {"type": "string", "description": "Optionele datum YYYY-MM-DD."},
            "time": {"type": "string", "description": "Optionele tijd HH:MM."},
            "datetime": {"type": "string", "description": "Optionele ISO datetime; heeft voorrang op date/time."},
            "search_for_arrival": {"type": "boolean", "description": "True wanneer de opgegeven tijd een gewenste aankomsttijd is."},
            "browser_lookup": {"type": "boolean", "description": "Probeer de officiële plannerpagina als zichtbare browserbron te lezen; standaard aan."},
            "query": {"type": "string", "description": "Originele gebruikersvraag voor audit/context."},
        },
        ["from_station", "to_station"],
    ),
    "ov9292_travel_advice": _tool_schema(
        "ov9292_travel_advice",
        "Read-only 9292/OV reisplanner via officiële plannerpagina waar mogelijk. Er wordt geen geheime 9292 API verondersteld; exacte tijden worden alleen genoemd als ze zichtbaar uit de officiële planner komen.",
        {
            "from_place": {"type": "string", "description": "Vertrekplaats, halte of station."},
            "to_place": {"type": "string", "description": "Aankomstplaats, halte of station."},
            "date": {"type": "string", "description": "Optionele datum YYYY-MM-DD."},
            "time": {"type": "string", "description": "Optionele tijd HH:MM."},
            "datetime": {"type": "string", "description": "Optionele ISO datetime; heeft voorrang op date/time."},
            "search_for_arrival": {"type": "boolean", "description": "True wanneer de opgegeven tijd een gewenste aankomsttijd is."},
            "browser_lookup": {"type": "boolean", "description": "Probeer de officiële plannerpagina als zichtbare browserbron te lezen; standaard aan."},
            "query": {"type": "string", "description": "Originele gebruikersvraag voor audit/context."},
        },
        [],
    ),
    "connector_intent_preview": _tool_schema(
        "connector_intent_preview",
        "Veilige placeholder voor niet-geïmplementeerde of muterende connector-intenten richting Gmail, Google Drive, GitHub en VPS/login/sync/deploy. Detecteert en gate zonder connector- of hostactie uit te voeren.",
        {
            "prompt": {"type": "string", "description": "Originele gebruikersvraag."},
            "services": {"type": "array", "items": {"type": "string"}, "description": "Gedetecteerde services, bv. gmail, google_drive, github, vps."},
            "categories": {"type": "array", "items": {"type": "string"}, "description": "Gedetecteerde categorieën."},
            "action_type": {"type": "string", "description": "read_only, private_read, mutating of private_mutating."},
            "approval": {"type": "string", "description": "Optioneel; alleen voor audit. Deze placeholder voert geen connectoractie uit."},
        },
        ["prompt"],
    ),
    "gmail_status": _tool_schema(
        "gmail_status",
        "Toont veilige Google Workspace/Gmail connectorstatus zonder mailboxinhoud of OAuth-token terug te geven. Read-only; geen Akkoord nodig.",
        {},
        [],
    ),
    "gmail_search": _tool_schema(
        "gmail_search",
        "Zoekt Gmail read-only via de bestaande Google Workspace adapter. Vereist exact Akkoord omdat mailboxinhoud privé is; verzendt of muteert nooit mail.",
        {
            "query": {"type": "string", "description": "Gmail zoekquery, bijvoorbeeld in:inbox of from:naam."},
            "max_results": {"type": "integer", "description": "Aantal berichten, maximaal 20."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor private Gmail-read."},
        },
        ["approval"],
    ),
    "google_drive_status": _tool_schema(
        "google_drive_status",
        "Toont veilige Google Drive connectorstatus voor Google Workspace en rclone zonder OAuth/rclone-tokenmateriaal terug te geven. Read-only; geen Akkoord nodig.",
        {},
        [],
    ),
    "google_drive_list": _tool_schema(
        "google_drive_list",
        "Lijst Google Drive bestanden read-only via rclone of Google Workspace adapter. Vereist exact Akkoord omdat Drive-inhoud privé is; upload/delete/sync ontbreken.",
        {
            "path": {"type": "string", "description": "Optioneel Drive-pad/folderpad."},
            "remote": {"type": "string", "description": "Optionele rclone remote."},
            "max_items": {"type": "integer", "description": "Maximaal aantal items, maximaal 100."},
            "max_depth": {"type": "integer", "description": "Maximale rclone diepte, maximaal 5."},
            "adapter": {"type": "string", "description": "auto, rclone of google_workspace."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor private Drive-read."},
        },
        ["approval"],
    ),
    "microsoft_graph_status": _tool_schema(
        "microsoft_graph_status",
        "Toont veilige Microsoft Graph/Microsoft 365 connectorstatus zonder OAuth-token of bearer-materiaal terug te geven. Read-only; geen Akkoord nodig.",
        {},
        [],
    ),
    "teams_list": _tool_schema(
        "teams_list",
        "Lijst joined Microsoft Teams read-only via de bestaande Microsoft Graph adapter. Vereist exact Akkoord omdat Teams-lidmaatschap privé is.",
        {
            "max_items": {"type": "integer", "description": "Aantal Teams, maximaal 50."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor private Teams-read."},
        },
        ["approval"],
    ),
    "onedrive_list": _tool_schema(
        "onedrive_list",
        "Lijst OneDrive rootbestanden read-only via de bestaande Microsoft Graph adapter. Vereist exact Akkoord omdat OneDrive-inhoud privé is; upload/delete/sync ontbreken.",
        {
            "path": {"type": "string", "description": "Optioneel pad voor toekomstige adapterondersteuning; huidige Graph foundation leest de root."},
            "max_items": {"type": "integer", "description": "Aantal bestanden, maximaal 100."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor private OneDrive-read."},
        },
        ["approval"],
    ),
    "outlook_read": _tool_schema(
        "outlook_read",
        "Leest Outlook berichten read-only via de bestaande Microsoft Graph adapter. Vereist exact Akkoord omdat mailboxinhoud privé is; verzendt of muteert nooit mail.",
        {
            "folder": {"type": "string", "description": "Mailfolder, standaard inbox."},
            "max_results": {"type": "integer", "description": "Aantal berichten, maximaal 25."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor private Outlook-read."},
        },
        ["approval"],
    ),
    "sharepoint_status": _tool_schema(
        "sharepoint_status",
        "Toont veilige SharePoint adapterstatus zonder OAuth-token of bearer-materiaal terug te geven. Read-only; geen Akkoord nodig.",
        {},
        [],
    ),
    "sharepoint_sites": _tool_schema(
        "sharepoint_sites",
        "Lijst SharePoint sites read-only via de bestaande SharePoint/Microsoft Graph adapters. Vereist exact Akkoord omdat tenant-site-informatie privé is.",
        {
            "search": {"type": "string", "description": "Optionele SharePoint site search query; standaard *."},
            "max_items": {"type": "integer", "description": "Aantal sites, maximaal 100."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor private SharePoint-read."},
        },
        ["approval"],
    ),
    "sharepoint_libraries": _tool_schema(
        "sharepoint_libraries",
        "Lijst SharePoint libraries/lists read-only via de bestaande SharePoint adapter. Vereist exact Akkoord omdat tenant-library-informatie privé is.",
        {
            "site": {"type": "string", "description": "Site-id of URL."},
            "site_id": {"type": "string", "description": "Optionele Graph site-id."},
            "site_url": {"type": "string", "description": "Optionele SharePoint site URL."},
            "max_items": {"type": "integer", "description": "Aantal libraries, maximaal 100."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor private SharePoint library-read."},
        },
        ["approval"],
    ),
    "github_status": _tool_schema(
        "github_status",
        "Toont veilige GitHub connectorstatus en tokenbron/maskering zonder token terug te geven. Read-only; geen Akkoord nodig.",
        {},
        [],
    ),
    "github_repo": _tool_schema(
        "github_repo",
        "Haalt read-only GitHub repository metadata op. Publieke repo's vereisen geen Akkoord; private metadata wordt geblokkeerd tenzij exact Akkoord is meegegeven.",
        {
            "repo": {"type": "string", "description": "owner/repo of github.com/owner/repo URL."},
            "approval": {"type": "string", "description": "Alleen nodig voor private repository metadata."},
        },
        ["repo"],
    ),
    "github_search_repositories": _tool_schema(
        "github_search_repositories",
        "Zoekt publieke GitHub repositories read-only via de officiële API. Forceert publieke resultaten en geeft nooit tokens terug.",
        {
            "query": {"type": "string", "description": "GitHub repository zoekvraag."},
            "limit": {"type": "integer", "description": "Aantal repositories, maximaal 20."},
            "approval": {"type": "string", "description": "Gereserveerd voor audit; private zoekopdrachten blijven geblokkeerd."},
        },
        ["query"],
    ),
    "vps_status": _tool_schema(
        "vps_status",
        "Toont veilige VPS deploy-profielstatus zonder credentials. Remote target staat vast op /var/www/philip-wintrip.nl/html/Ouroboros/.",
        {},
        [],
    ),
    "vps_login_check": _tool_schema(
        "vps_login_check",
        "Controleert read-only of SSH BatchMode login via host SSH agent/config mogelijk is. Geeft nooit credentials terug en muteert niets.",
        {
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden, begrensd door de adapter."},
        },
        [],
    ),
    "vps_sync_preview": _tool_schema(
        "vps_sync_preview",
        "Maakt een rsync --dry-run preview naar de vaste Ouroboros VPS target. Muteert niets en sluit secrets/state standaard uit.",
        {
            "remote_path": {"type": "string", "description": "Leeg voor vaste root of veilige child onder /var/www/philip-wintrip.nl/html/Ouroboros/."},
            "source_path": {"type": "string", "description": "Optioneel workspace-subpad; standaard de WintripAI workspace."},
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden."},
        },
        [],
    ),
    "vps_sync_execute": _tool_schema(
        "vps_sync_execute",
        "Voert rsync naar de vaste Ouroboros VPS target uit. Vereist exact Akkoord; secrets/state blijven standaard uitgesloten.",
        {
            "remote_path": {"type": "string", "description": "Leeg voor vaste root of veilige child onder /var/www/philip-wintrip.nl/html/Ouroboros/."},
            "source_path": {"type": "string", "description": "Optioneel workspace-subpad; standaard de WintripAI workspace."},
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor echte sync."},
        },
        ["approval"],
    ),
    "vps_ui_sync_preview": _tool_schema(
        "vps_ui_sync_preview",
        "Maakt een dry-run van de gebouwde Cockpit UI artifact sync: ouroboros_cockpit/dist/ naar de vaste VPS Ouroboros webroot. Muteert niets.",
        {
            "remote_path": {"type": "string", "description": "Leeg voor vaste webroot of veilige child onder /var/www/philip-wintrip.nl/html/Ouroboros/."},
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden."},
        },
        [],
    ),
    "vps_ui_sync_execute": _tool_schema(
        "vps_ui_sync_execute",
        "Bouwt de lokale Cockpit UI en synchroniseert de dist artifact naar de VPS webroot. Vereist exact Akkoord.",
        {
            "remote_path": {"type": "string", "description": "Leeg voor vaste webroot of veilige child onder /var/www/philip-wintrip.nl/html/Ouroboros/."},
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden."},
            "build_first": {"type": "boolean", "description": "Bouw de UI lokaal voordat rsync start; standaard true."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor build + echte sync."},
        },
        ["approval"],
    ),
    "chroma_sync_status": _tool_schema(
        "chroma_sync_status",
        "Toont lokale en VPS ChromaDB status via SSH/host bridge zonder documenten of secrets terug te geven.",
        {
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden."},
        },
        [],
    ),
    "chroma_sync_preview": _tool_schema(
        "chroma_sync_preview",
        "Maakt een niet-muterende preview van welke Chroma records lokaal en op de VPS ontbreken. Geeft geen raw documenten terug.",
        {
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden."},
        },
        [],
    ),
    "chroma_sync_execute": _tool_schema(
        "chroma_sync_execute",
        "Voert een bidirectionele ChromaDB merge uit via SSH: VPS records naar lokaal en lokale records naar VPS. Vereist exact Akkoord.",
        {
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconden."},
            "approval": {"type": "string", "description": "Exact 'Akkoord' vereist voor de merge."},
        },
        ["approval"],
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
        "Verstuurt mail via de Google Workspace Gmail send-adapter wanneer OAuth is geconfigureerd. Vereist Akkoord; claimt geen verzending zonder bewijs.",
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
            elif not (connector_gate := _connector_gate_for_tool(tool_name)).get("enabled", True):
                result = _connector_disabled_result(tool_name, connector_gate)
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
                    browser_lookup=_bool_arg(args.get("browser_lookup"), default=True),
                    query=str(args.get("query") or args.get("prompt") or ""),
                )
            elif tool_name == "ov9292_travel_advice":
                result = self.ov9292_travel_advice(
                    from_place=str(args.get("from_place") or args.get("from_station") or args.get("from") or ""),
                    to_place=str(args.get("to_place") or args.get("to_station") or args.get("to") or ""),
                    date=str(args.get("date") or ""),
                    time_value=str(args.get("time") or ""),
                    datetime_value=str(args.get("datetime") or args.get("dateTime") or ""),
                    search_for_arrival=bool(args.get("search_for_arrival", False)),
                    browser_lookup=_bool_arg(args.get("browser_lookup"), default=True),
                    query=str(args.get("query") or args.get("prompt") or ""),
                )
            elif tool_name == "connector_intent_preview":
                result = self.connector_intent_preview(
                    prompt=str(args.get("prompt") or args.get("query") or ""),
                    services=list(args.get("services") or []),
                    categories=list(args.get("categories") or []),
                    action_type=str(args.get("action_type") or ""),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "gmail_status":
                result = self.gmail_status()
            elif tool_name == "gmail_search":
                result = self.gmail_search(
                    query=str(args.get("query") or args.get("q") or "in:inbox"),
                    max_results=_int(args.get("max_results") or args.get("limit"), default=5),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "google_drive_status":
                result = self.google_drive_status()
            elif tool_name == "google_drive_list":
                result = self.google_drive_list(
                    path=str(args.get("path") or args.get("folder") or ""),
                    remote=str(args.get("remote") or ""),
                    max_items=_int(args.get("max_items") or args.get("limit"), default=25),
                    max_depth=_int(args.get("max_depth"), default=1),
                    adapter=str(args.get("adapter") or "auto"),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "microsoft_graph_status":
                result = self.microsoft_graph_status()
            elif tool_name == "teams_list":
                result = self.teams_list(
                    max_items=_int(args.get("max_items") or args.get("limit"), default=25),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "onedrive_list":
                result = self.onedrive_list(
                    path=str(args.get("path") or args.get("folder") or ""),
                    max_items=_int(args.get("max_items") or args.get("limit"), default=25),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "outlook_read":
                result = self.outlook_read(
                    folder=str(args.get("folder") or "inbox"),
                    max_results=_int(args.get("max_results") or args.get("limit"), default=10),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "sharepoint_status":
                result = self.sharepoint_status()
            elif tool_name == "sharepoint_sites":
                result = self.sharepoint_sites(
                    search=str(args.get("search") or args.get("query") or "*"),
                    max_items=_int(args.get("max_items") or args.get("limit"), default=25),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "sharepoint_libraries":
                result = self.sharepoint_libraries(
                    site=str(args.get("site") or args.get("site_id") or args.get("site_url") or ""),
                    max_items=_int(args.get("max_items") or args.get("limit"), default=25),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "github_status":
                result = self.github_status()
            elif tool_name == "github_repo":
                result = self.github_repo(
                    repo=str(args.get("repo") or args.get("repository") or args.get("url") or ""),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "github_search_repositories":
                result = self.github_search_repositories(
                    query=str(args.get("query") or args.get("q") or args.get("prompt") or ""),
                    limit=_int(args.get("limit") or args.get("max_results"), default=5),
                    approval=str(args.get("approval") or ""),
                )
            elif tool_name == "vps_status":
                result = self.vps_status()
            elif tool_name == "vps_login_check":
                result = self.vps_login_check(
                    timeout_seconds=_int(args.get("timeout_seconds"), default=120),
                )
            elif tool_name == "vps_sync_preview":
                result = self.vps_sync_preview(
                    remote_path=str(args.get("remote_path") or args.get("remote_target") or ""),
                    source_path=str(args.get("source_path") or ""),
                    timeout_seconds=_int(args.get("timeout_seconds"), default=120),
                )
            elif tool_name == "vps_sync_execute":
                result = self.vps_sync_execute(
                    approval=str(args.get("approval") or ""),
                    remote_path=str(args.get("remote_path") or args.get("remote_target") or ""),
                    source_path=str(args.get("source_path") or ""),
                    timeout_seconds=_int(args.get("timeout_seconds"), default=120),
                )
            elif tool_name == "vps_ui_sync_preview":
                result = self.vps_ui_sync_preview(
                    remote_path=str(args.get("remote_path") or args.get("remote_target") or ""),
                    timeout_seconds=_int(args.get("timeout_seconds"), default=120),
                )
            elif tool_name == "vps_ui_sync_execute":
                result = self.vps_ui_sync_execute(
                    approval=str(args.get("approval") or ""),
                    remote_path=str(args.get("remote_path") or args.get("remote_target") or ""),
                    timeout_seconds=_int(args.get("timeout_seconds"), default=120),
                    build_first=_bool_arg(args.get("build_first"), default=True),
                )
            elif tool_name == "chroma_sync_status":
                result = self.chroma_sync_status(
                    timeout_seconds=_int(args.get("timeout_seconds"), default=45),
                )
            elif tool_name == "chroma_sync_preview":
                result = self.chroma_sync_preview(
                    timeout_seconds=_int(args.get("timeout_seconds"), default=120),
                )
            elif tool_name == "chroma_sync_execute":
                result = self.chroma_sync_execute(
                    approval=str(args.get("approval") or ""),
                    timeout_seconds=_int(args.get("timeout_seconds"), default=300),
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
        result.setdefault(
            "tool_trace",
            {
                "tool_name": result.get("tool_name", tool_name),
                "status": result.get("status", "unknown"),
                "source": result.get("source", "agent_tools"),
                "approval_status": result.get("approval_status", "not_required"),
                "duration_seconds": result["duration_seconds"],
                "stored_to_memory": bool(result.get("stored_to_memory")),
                "fake_success": False,
            },
        )
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
        browser_lookup: bool | None = None,
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
            "source": "NS Reisplanner official planner page",
            "api_available": False,
            "api_mode": "disabled_by_default",
        }
        browser = _official_travel_browser_lookup(
            provider="ns",
            planner_url=planner_url,
            from_place=from_station,
            to_place=to_station,
            date_time=date_time,
            search_for_arrival=search_for_arrival,
            enabled=browser_lookup,
        )
        if not _ns_api_enabled():
            payload = {**base_payload, "configured": False, "api_skipped": True, "browser_lookup": browser}
            return _official_planner_tool_result(
                tool_name="ns_travel_advice",
                payload=payload,
                browser=browser,
                planner_links=[planner_url],
                source="ns_travel_advice",
                fallback_intro=(
                    "Ik gebruik voor NS standaard de officiële Reisplanner-pagina in plaats van de verborgen/API-route. "
                    "Er zijn geen tijden verzonnen uit snippets."
                ),
                metadata_source_type="ns_travel_advice",
            )

        key = _ns_api_key()
        if not key:
            payload = {**base_payload, "configured": False, "missing_api_key": True, "api_requested": True, "browser_lookup": browser}
            return _official_planner_tool_result(
                tool_name="ns_travel_advice",
                payload=payload,
                browser=browser,
                planner_links=[planner_url],
                source="ns_travel_advice",
                fallback_intro=(
                    "NS API opt-in staat aan, maar de API key ontbreekt. "
                    "Ik val terug op de officiële Reisplanner-pagina en verzin geen tijden."
                ),
                metadata_source_type="ns_travel_advice",
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
        payload = {
            **base_payload,
            "configured": True,
            "api_available": True,
            "api_mode": "opt_in",
            "authoritative": True,
            "source": "official_ns_api_opt_in",
            "advice": summary,
            "raw": raw,
        }
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

    def ov9292_travel_advice(
        self,
        *,
        from_place: str = "",
        to_place: str = "",
        date: str = "",
        time_value: str = "",
        datetime_value: str = "",
        search_for_arrival: bool = False,
        browser_lookup: bool | None = None,
        query: str = "",
    ) -> dict[str, Any]:
        from_place = " ".join(str(from_place or "").split())
        to_place = " ".join(str(to_place or "").split())
        date_time = _ns_datetime(date=date, time_value=time_value, datetime_value=datetime_value)
        links = _ov9292_planner_links(from_place, to_place, date_time=date_time, search_for_arrival=search_for_arrival, query=query)
        planner_url = links[1] if len(links) > 1 and "/reisadvies" in links[1] else links[0]
        browser = _official_travel_browser_lookup(
            provider="9292",
            planner_url=planner_url,
            from_place=from_place,
            to_place=to_place,
            date_time=date_time,
            search_for_arrival=search_for_arrival,
            enabled=browser_lookup,
        )
        payload = {
            "from_place": from_place,
            "to_place": to_place,
            "date": date,
            "time": time_value,
            "datetime": date_time,
            "search_for_arrival": bool(search_for_arrival),
            "query": query,
            "planner_url": planner_url,
            "official_links": links,
            "authoritative": False,
            "configured": False,
            "api_available": False,
            "source": "9292 official planner page",
            "browser_lookup": browser,
            "scraped": False,
            "session_material_used": False,
        }
        return _official_planner_tool_result(
            tool_name="ov9292_travel_advice",
            payload=payload,
            browser=browser,
            planner_links=links,
            source="ov9292_travel_advice",
            fallback_intro=(
                "Ik gebruik voor 9292 de officiële plannerpagina en geen verborgen API of login/session-materiaal. "
                "Er zijn geen tijden verzonnen uit snippets."
            ),
            metadata_source_type="ov9292_travel_advice",
        )

    def connector_intent_preview(
        self,
        *,
        prompt: str,
        services: list[Any] | None = None,
        categories: list[Any] | None = None,
        action_type: str = "",
        approval: str = "",
    ) -> dict[str, Any]:
        clean_prompt = " ".join(str(prompt or "").split())
        clean_services = _connector_services_from_prompt(clean_prompt, services or [])
        clean_categories = _unique_texts([*(str(item) for item in (categories or [])), "connector"])
        mutating = _connector_prompt_mutating(clean_prompt) or str(action_type or "").lower() in {"mutating", "private_mutating"}
        private = bool(clean_services) or str(action_type or "").lower().startswith("private")
        final_action_type = "private_mutating" if private and mutating else ("private_read" if private else ("mutating" if mutating else "read_only"))
        approval_ok = approval_matches(approval)
        ziel_policy = ziel_guardrail_note()
        payload = {
            "prompt_preview": clean_prompt[:500],
            "services": clean_services,
            "categories": clean_categories,
            "action_type": final_action_type,
            "approval_required": True,
            "approval_present": approval_ok,
            "executed": False,
            "preview_only": True,
            "adapters_started": [],
            "blocked_tools": _connector_blocked_tools(clean_services, final_action_type),
            "ziel_policy": ziel_policy,
            "policy": "Gmail/Drive/GitHub/VPS gewone-chat intenten worden hier alleen herkend en veilig gegate; adapteruitvoering is bewust buiten deze backend-foundation subtaak gehouden.",
            "secrets_returned": False,
        }
        stdout = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        if approval_ok:
            status = "preview"
            approval_status = "approved_preview_only"
            next_action = "Connector/VPS intent is goedgekeurd maar deze foundation voert geen Gmail/Drive/GitHub/VPS adapter uit; start een aparte adapter-subtaak."
        else:
            status = "blocked"
            approval_status = "pending_philip_akkoord"
            next_action = "Private of muterende connector/VPS intent gedetecteerd; uitvoering blijft geblokkeerd. Gebruik een aparte goedgekeurde adapter-subtaak."
        return _tool_result(
            "connector_intent_preview",
            status,
            result=payload,
            stdout=stdout,
            stderr="" if status == "preview" else "Private/mutating connector intent gated; no adapter executed.",
            source="connector_intent_preview",
            approval_status=approval_status,
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "connector_intent_preview", "taint": "private_intent_metadata_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action=next_action,
        )

    def gmail_status(self) -> dict[str, Any]:
        try:
            from controller.google_workspace_adapter import GoogleWorkspaceAdapter

            raw = GoogleWorkspaceAdapter().status()
        except Exception as exc:
            return _tool_result(
                "gmail_status",
                "error",
                stderr=str(exc),
                source="google_workspace:gmail_status",
                next_action="Controleer de Google Workspace adapterconfiguratie zonder tokens te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        payload["secrets_returned"] = False
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        return _tool_result(
            "gmail_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="google_workspace:gmail_status",
            approval_status="not_required_status",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "gmail_connector_status", "taint": "connector_status_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik gmail_search met exact Akkoord wanneer Philip private mailboxresultaten wil lezen.",
        )

    def gmail_search(self, query: str, max_results: int = 5, approval: str = "") -> dict[str, Any]:
        clean_query = " ".join(str(query or "in:inbox").split()) or "in:inbox"
        limit = max(1, min(int(max_results or 5), 20))
        if not approval_matches(approval):
            ziel_policy = ziel_guardrail_note()
            payload = {"query": clean_query, "max_results": limit, "approval_required": True, "read_only": True, "executed": False, "secrets_returned": False, "ziel_policy": ziel_policy}
            return _tool_result(
                "gmail_search",
                "blocked",
                result=payload,
                stdout=_stringify(payload),
                stderr="Gmail search is private mailbox data and requires exact Akkoord.",
                source="google_workspace:gmail_search",
                approval_status="pending_philip_akkoord",
                metadata_11d={"dimension_count": 11, "source_type": "gmail_private_read_gate", "taint": "private_user_data", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
                next_action="Vraag Philip om exact Akkoord voordat Gmail-resultaten worden gelezen.",
            )
        try:
            from controller.google_workspace_adapter import GoogleWorkspaceAdapter

            raw = GoogleWorkspaceAdapter(live_api_enabled=True).search_gmail(query=clean_query, approval=approval, max_results=limit)
        except Exception as exc:
            return _tool_result(
                "gmail_search",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="google_workspace:gmail_search",
                approval_status="approved",
                next_action="Controleer Google OAuth/scopes/live-api instelling zonder tokenmateriaal te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        raw_status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        status = "success" if raw_status == "success" else raw_status
        return _tool_result(
            "gmail_search",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source="google_workspace:gmail_search",
            approval_status="approved",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "gmail_private_readonly", "taint": "private_user_data", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Vat de gevonden mail samen of maak een concept; mail verzenden blijft buiten deze tool.",
        )

    def google_drive_status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": "unknown", "adapters": {}, "secrets_returned": False, "fake_success": False}
        statuses: list[str] = []
        try:
            from controller.google_workspace_adapter import GoogleWorkspaceAdapter

            google_status = _sanitize_connector_payload(GoogleWorkspaceAdapter().status())
            payload["adapters"]["google_workspace"] = google_status
            statuses.append(str(google_status.get("status") or "unknown"))
        except Exception as exc:
            payload["adapters"]["google_workspace"] = {"status": "error", "reason": _redact_operational_text(str(exc)), "fake_success": False}
        try:
            from controller.rclone_drive_adapter import RcloneDriveAdapter

            rclone_status = _sanitize_connector_payload(RcloneDriveAdapter().status())
            payload["adapters"]["rclone_drive"] = rclone_status
            statuses.append(str(rclone_status.get("status") or "unknown"))
        except Exception as exc:
            payload["adapters"]["rclone_drive"] = {"status": "error", "reason": _redact_operational_text(str(exc)), "fake_success": False}
        payload["status"] = "ready" if any(item in {"connected", "ready", "success", "online"} for item in statuses) else "unavailable"
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        return _tool_result(
            "google_drive_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="google_drive:status",
            approval_status="not_required_status",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "google_drive_connector_status", "taint": "connector_status_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik google_drive_list met exact Akkoord wanneer Philip private Drive-inhoud wil lezen.",
        )

    def google_drive_list(
        self,
        *,
        path: str = "",
        remote: str = "",
        max_items: int = 25,
        max_depth: int = 1,
        adapter: str = "auto",
        approval: str = "",
    ) -> dict[str, Any]:
        limit = max(1, min(int(max_items or 25), 100))
        depth = max(1, min(int(max_depth or 1), 5))
        clean_adapter = str(adapter or "auto").strip().lower().replace("-", "_")
        if clean_adapter in {"google", "workspace"}:
            clean_adapter = "google_workspace"
        if clean_adapter not in {"auto", "rclone", "google_workspace"}:
            return _tool_result(
                "google_drive_list",
                "error",
                stderr="adapter must be auto, rclone or google_workspace.",
                source="google_drive:list",
                next_action="Kies adapter=auto, rclone of google_workspace.",
            )
        if not approval_matches(approval):
            ziel_policy = ziel_guardrail_note()
            payload = {"path": path, "remote": remote, "max_items": limit, "approval_required": True, "read_only": True, "executed": False, "secrets_returned": False, "ziel_policy": ziel_policy}
            return _tool_result(
                "google_drive_list",
                "blocked",
                result=payload,
                stdout=_stringify(payload),
                stderr="Google Drive listing is private data and requires exact Akkoord.",
                source="google_drive:list",
                approval_status="pending_philip_akkoord",
                metadata_11d={"dimension_count": 11, "source_type": "google_drive_private_read_gate", "taint": "private_user_data", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
                next_action="Vraag Philip om exact Akkoord voordat Drive-bestanden worden gelijst.",
            )
        raw: dict[str, Any] | None = None
        adapter_used = ""
        errors: list[dict[str, Any]] = []
        if clean_adapter in {"auto", "rclone"}:
            try:
                from controller.rclone_drive_adapter import RcloneDriveAdapter

                rclone = RcloneDriveAdapter()
                rclone_status = rclone.status()
                if clean_adapter == "rclone" or str(rclone_status.get("status") or "") in {"ready", "success", "online"}:
                    raw = rclone.list_drive_files(approval=approval, remote=remote, path=path, max_items=limit, max_depth=depth)
                    adapter_used = "rclone_drive"
            except Exception as exc:
                errors.append({"adapter": "rclone_drive", "status": "error", "reason": _redact_operational_text(str(exc))})
        if raw is None and clean_adapter in {"auto", "google_workspace"}:
            try:
                from controller.google_workspace_adapter import GoogleWorkspaceAdapter

                raw = GoogleWorkspaceAdapter(live_api_enabled=True).list_drive_files(approval=approval, page_size=limit)
                adapter_used = "google_workspace"
            except Exception as exc:
                errors.append({"adapter": "google_workspace", "status": "error", "reason": _redact_operational_text(str(exc))})
        if raw is None:
            raw = {"status": "error", "operation": "list_drive_files", "reason": "No Google Drive adapter could be selected.", "errors": errors, "fake_success": False}
        payload = _sanitize_connector_payload({**raw, "adapter_used": adapter_used or clean_adapter, "errors": errors, "read_only": True, "secrets_returned": False})
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        raw_status = str(raw.get("status") or "error")
        status = "success" if raw_status == "success" else raw_status
        return _tool_result(
            "google_drive_list",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source=f"google_drive:list:{adapter_used or clean_adapter}",
            approval_status="approved",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "google_drive_private_readonly", "taint": "private_user_data", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik de Drive-listing alleen als private read-only context; upload/delete/sync zijn niet beschikbaar in deze tool.",
        )

    def microsoft_graph_status(self) -> dict[str, Any]:
        try:
            from controller.microsoft_graph_adapter import MicrosoftGraphAdapter

            raw = MicrosoftGraphAdapter().status()
        except Exception as exc:
            return _tool_result(
                "microsoft_graph_status",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="microsoft_graph:status",
                next_action="Controleer Microsoft Graph adapterconfiguratie zonder tokens te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        payload["secrets_returned"] = False
        return _tool_result(
            "microsoft_graph_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="microsoft_graph:status",
            approval_status="not_required_status",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "microsoft_graph_connector_status", "taint": "connector_status_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik teams_list, onedrive_list of outlook_read met exact Akkoord voor private Microsoft 365 reads.",
        )

    def teams_list(self, *, max_items: int = 25, approval: str = "") -> dict[str, Any]:
        limit = max(1, min(int(max_items or 25), 50))
        if not approval_matches(approval):
            return _private_connector_read_blocked_result(
                "teams_list",
                payload={"max_items": limit},
                source="microsoft_graph:teams_list",
                source_type="microsoft_teams_private_read_gate",
                stderr="Microsoft Teams listing is private Microsoft 365 data and requires exact Akkoord.",
                next_action="Vraag Philip om exact Akkoord voordat Teams-lidmaatschap wordt gelezen.",
            )
        try:
            from controller.microsoft_graph_adapter import MicrosoftGraphAdapter

            raw = MicrosoftGraphAdapter().list_teams(approval=approval)
        except Exception as exc:
            return _tool_result(
                "teams_list",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="microsoft_graph:teams_list",
                approval_status="approved",
                next_action="Controleer Microsoft Graph token/scopes/live-api instelling zonder tokenmateriaal te delen.",
            )
        return _private_connector_read_result(
            "teams_list",
            raw,
            source="microsoft_graph:teams_list",
            source_type="microsoft_teams_private_readonly",
            limit=limit,
            next_action="Gebruik Teams-resultaten alleen als private read-only context; Teams-mutaties zijn niet beschikbaar in deze tool.",
        )

    def onedrive_list(self, *, path: str = "", max_items: int = 25, approval: str = "") -> dict[str, Any]:
        limit = max(1, min(int(max_items or 25), 100))
        if not approval_matches(approval):
            return _private_connector_read_blocked_result(
                "onedrive_list",
                payload={"path": path, "max_items": limit},
                source="microsoft_graph:onedrive_list",
                source_type="onedrive_private_read_gate",
                stderr="OneDrive listing is private Microsoft 365 data and requires exact Akkoord.",
                next_action="Vraag Philip om exact Akkoord voordat OneDrive-bestanden worden gelijst.",
            )
        try:
            from controller.microsoft_graph_adapter import MicrosoftGraphAdapter

            raw = MicrosoftGraphAdapter().list_onedrive_files(approval=approval)
        except Exception as exc:
            return _tool_result(
                "onedrive_list",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="microsoft_graph:onedrive_list",
                approval_status="approved",
                next_action="Controleer Microsoft Graph token/scopes/live-api instelling zonder tokenmateriaal te delen.",
            )
        return _private_connector_read_result(
            "onedrive_list",
            {**raw, "requested_path": path},
            source="microsoft_graph:onedrive_list",
            source_type="onedrive_private_readonly",
            limit=limit,
            next_action="Gebruik OneDrive-resultaten alleen als private read-only context; upload/delete/sync zijn niet beschikbaar in deze tool.",
        )

    def outlook_read(self, *, folder: str = "inbox", max_results: int = 10, approval: str = "") -> dict[str, Any]:
        clean_folder = " ".join(str(folder or "inbox").split()) or "inbox"
        limit = max(1, min(int(max_results or 10), 25))
        if not approval_matches(approval):
            return _private_connector_read_blocked_result(
                "outlook_read",
                payload={"folder": clean_folder, "max_results": limit},
                source="microsoft_graph:outlook_read",
                source_type="outlook_private_read_gate",
                stderr="Outlook read is private mailbox data and requires exact Akkoord.",
                next_action="Vraag Philip om exact Akkoord voordat Outlook-berichten worden gelezen.",
            )
        try:
            from controller.microsoft_graph_adapter import MicrosoftGraphAdapter

            raw = MicrosoftGraphAdapter().read_outlook_messages(
                approval=approval,
                folder=clean_folder,
                max_results=limit,
            )
        except Exception as exc:
            return _tool_result(
                "outlook_read",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="microsoft_graph:outlook_read",
                approval_status="approved",
                next_action="Controleer Microsoft Graph token/scopes/live-api instelling zonder tokenmateriaal te delen.",
            )
        return _private_connector_read_result(
            "outlook_read",
            raw,
            source="microsoft_graph:outlook_read",
            source_type="outlook_private_readonly",
            limit=limit,
            next_action="Vat de gevonden Outlook-berichten samen of maak een concept; mail verzenden blijft buiten deze tool.",
        )

    def sharepoint_status(self) -> dict[str, Any]:
        try:
            from controller.sharepoint_pnp_adapter import SharePointPnPAdapter

            raw = SharePointPnPAdapter().status()
        except Exception as exc:
            return _tool_result(
                "sharepoint_status",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="sharepoint:status",
                next_action="Controleer SharePoint adapterconfiguratie zonder tokens te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        payload["secrets_returned"] = False
        return _tool_result(
            "sharepoint_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="sharepoint:status",
            approval_status="not_required_status",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "sharepoint_connector_status", "taint": "connector_status_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik sharepoint_sites of sharepoint_libraries met exact Akkoord voor private SharePoint reads.",
        )

    def sharepoint_sites(self, *, search: str = "*", max_items: int = 25, approval: str = "") -> dict[str, Any]:
        clean_search = " ".join(str(search or "*").split()) or "*"
        limit = max(1, min(int(max_items or 25), 100))
        if not approval_matches(approval):
            return _private_connector_read_blocked_result(
                "sharepoint_sites",
                payload={"search": clean_search, "max_items": limit},
                source="sharepoint:sites",
                source_type="sharepoint_sites_private_read_gate",
                stderr="SharePoint site listing is private Microsoft 365 tenant data and requires exact Akkoord.",
                next_action="Vraag Philip om exact Akkoord voordat SharePoint sites worden gelezen.",
            )
        try:
            from controller.sharepoint_pnp_adapter import SharePointPnPAdapter

            raw = SharePointPnPAdapter().list_site_collections(approval=approval, search=clean_search)
        except Exception as exc:
            return _tool_result(
                "sharepoint_sites",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="sharepoint:sites",
                approval_status="approved",
                next_action="Controleer SharePoint/Microsoft Graph token/scopes zonder tokenmateriaal te delen.",
            )
        return _private_connector_read_result(
            "sharepoint_sites",
            raw,
            source="sharepoint:sites",
            source_type="sharepoint_sites_private_readonly",
            limit=limit,
            next_action="Gebruik SharePoint sites alleen als private read-only context; permission- of workflow-mutaties blijven buiten deze tool.",
        )

    def sharepoint_libraries(self, *, site: str = "", max_items: int = 25, approval: str = "") -> dict[str, Any]:
        clean_site = " ".join(str(site or "").split())
        limit = max(1, min(int(max_items or 25), 100))
        if not approval_matches(approval):
            return _private_connector_read_blocked_result(
                "sharepoint_libraries",
                payload={"site": clean_site, "max_items": limit},
                source="sharepoint:libraries",
                source_type="sharepoint_libraries_private_read_gate",
                stderr="SharePoint library listing is private Microsoft 365 tenant data and requires exact Akkoord.",
                next_action="Vraag Philip om exact Akkoord voordat SharePoint libraries worden gelezen.",
            )
        try:
            from controller.sharepoint_pnp_adapter import SharePointPnPAdapter

            raw = SharePointPnPAdapter().list_libraries(site=clean_site, approval=approval)
        except Exception as exc:
            return _tool_result(
                "sharepoint_libraries",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="sharepoint:libraries",
                approval_status="approved",
                next_action="Controleer SharePoint/Microsoft Graph token/scopes zonder tokenmateriaal te delen.",
            )
        return _private_connector_read_result(
            "sharepoint_libraries",
            raw,
            source="sharepoint:libraries",
            source_type="sharepoint_libraries_private_readonly",
            limit=limit,
            next_action="Gebruik SharePoint libraries alleen als private read-only context; library writes blijven buiten deze tool.",
        )

    def github_status(self) -> dict[str, Any]:
        try:
            from controller.github_adapter import GitHubAdapter

            raw = GitHubAdapter().status()
        except Exception as exc:
            return _tool_result(
                "github_status",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="github:status",
                next_action="Controleer GitHub token/env/API-key-store configuratie zonder tokens te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        return _tool_result(
            "github_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="github:status",
            approval_status="not_required_status",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "github_connector_status", "taint": "connector_status_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik github_repo of github_search_repositories voor publieke read-only GitHub metadata.",
        )

    def github_repo(self, repo: str, approval: str = "") -> dict[str, Any]:
        try:
            from controller.github_adapter import GitHubAdapter

            raw = GitHubAdapter().get_repository(repo, approval=approval)
        except Exception as exc:
            return _tool_result(
                "github_repo",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="github:repo",
                next_action="Controleer de repositorynaam owner/repo en GitHub adapterstatus.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error")
        approval_status = str(raw.get("approval_status") or ("pending_philip_akkoord" if status == "blocked" else "not_required_public_readonly"))
        return _tool_result(
            "github_repo",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source="github:repo",
            approval_status=approval_status,
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "github_repository_metadata", "taint": "public_web_api" if status == "success" else "connector_guardrail", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik deze metadata read-only; GitHub writes/issues/pushes zijn niet beschikbaar in deze tool.",
        )

    def github_search_repositories(self, query: str, limit: int = 5, approval: str = "") -> dict[str, Any]:
        try:
            from controller.github_adapter import GitHubAdapter

            raw = GitHubAdapter().search_repositories(query, limit=max(1, min(int(limit or 5), 20)), approval=approval)
        except Exception as exc:
            return _tool_result(
                "github_search_repositories",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="github:search_repositories",
                next_action="Controleer GitHub adapterstatus of probeer een kortere publieke zoekquery.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error")
        approval_status = str(raw.get("approval_status") or ("pending_philip_akkoord" if status == "blocked" else "not_required_public_readonly"))
        return _tool_result(
            "github_search_repositories",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source="github:search_repositories",
            approval_status=approval_status,
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "github_repository_search", "taint": "public_web_api" if status == "success" else "connector_guardrail", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik publieke GitHub-resultaten als read-only context; mutaties blijven geblokkeerd.",
        )

    def vps_status(self) -> dict[str, Any]:
        try:
            from controller.vps_deploy_adapter import VPSDeployAdapter

            raw = VPSDeployAdapter().status()
        except Exception as exc:
            return _tool_result(
                "vps_status",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="vps_deploy:status",
                next_action="Controleer VPS profielmetadata zonder credentials te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        return _tool_result(
            "vps_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="vps_deploy:status",
            approval_status="not_required_status",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "vps_deploy_status", "taint": "connector_status_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik vps_sync_preview voor een niet-muterende dry-run; vps_sync_execute vereist exact Akkoord.",
        )

    def vps_login_check(self, timeout_seconds: int = 120) -> dict[str, Any]:
        try:
            from controller.vps_deploy_adapter import VPSDeployAdapter

            raw = VPSDeployAdapter().login_check(timeout_seconds=max(5, min(int(timeout_seconds or 120), 300)))
        except Exception as exc:
            return _tool_result(
                "vps_login_check",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="vps_deploy:login_check",
                next_action="Controleer host SSH agent/config zonder credentials in Ouroboros op te slaan.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "vps_login_check",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source="vps_deploy:login_check",
            approval_status="not_required_readonly",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "vps_login_check", "taint": "host_metadata_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Als login_ok=true kan vps_sync_preview veilig een rsync dry-run maken; geen credentials worden teruggegeven.",
        )

    def vps_sync_preview(self, *, remote_path: str = "", source_path: str = "", timeout_seconds: int = 120) -> dict[str, Any]:
        try:
            from controller.vps_deploy_adapter import VPSDeployAdapter

            raw = VPSDeployAdapter().sync_preview(
                remote_path=remote_path,
                source_path=source_path,
                timeout_seconds=max(10, min(int(timeout_seconds or 120), 900)),
            )
        except Exception as exc:
            return _tool_result(
                "vps_sync_preview",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="vps_deploy:sync_preview",
                next_action="Controleer VPS profielmetadata en rsync beschikbaarheid; preview mag niets muteren.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "vps_sync_preview",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "preview" else _stringify(payload),
            source="vps_deploy:sync_preview",
            approval_status="not_required_dry_run",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "vps_sync_preview", "taint": "host_deploy_metadata_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Review de dry-run output; voer pas vps_sync_execute uit met exact Akkoord als de preview klopt.",
        )

    def vps_sync_execute(self, *, approval: str = "", remote_path: str = "", source_path: str = "", timeout_seconds: int = 120) -> dict[str, Any]:
        if str(approval or "").strip() != "Akkoord":
            ziel_policy = ziel_guardrail_note()
            payload = {
                "remote_path": remote_path,
                "source_path": source_path,
                "approval_required": True,
                "executed": False,
                "mutated": False,
                "remote_target": "/var/www/philip-wintrip.nl/html/Ouroboros/",
                "secrets_returned": False,
                "ziel_policy": ziel_policy,
            }
            return _tool_result(
                "vps_sync_execute",
                "blocked",
                result=payload,
                stdout=_stringify(payload),
                stderr="VPS sync execution requires exact Akkoord.",
                source="vps_deploy:sync_execute",
                approval_status="pending_philip_akkoord",
                metadata_11d={"dimension_count": 11, "source_type": "vps_sync_execute_gate", "taint": "host_mutation_gate", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
                next_action="Vraag Philip om exact Akkoord na review van vps_sync_preview.",
            )
        try:
            from controller.vps_deploy_adapter import VPSDeployAdapter

            raw = VPSDeployAdapter().sync_execute(
                approval=approval,
                remote_path=remote_path,
                source_path=source_path,
                timeout_seconds=max(10, min(int(timeout_seconds or 120), 900)),
            )
        except Exception as exc:
            return _tool_result(
                "vps_sync_execute",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="vps_deploy:sync_execute",
                approval_status="approved",
                next_action="Inspecteer de host bridge/rsync fout zonder secrets te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "vps_sync_execute",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source="vps_deploy:sync_execute",
            approval_status="approved",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "vps_sync_execute", "taint": "host_mutation_audit", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Controleer de VPS site en bewaar alleen auditmetadata; credentials zijn niet opgeslagen of teruggegeven.",
        )

    def vps_ui_sync_preview(self, *, remote_path: str = "", timeout_seconds: int = 120) -> dict[str, Any]:
        try:
            from controller.vps_deploy_adapter import VPSDeployAdapter

            raw = VPSDeployAdapter().ui_sync_preview(
                remote_path=remote_path,
                timeout_seconds=max(10, min(int(timeout_seconds or 120), 900)),
            )
        except Exception as exc:
            return _tool_result(
                "vps_ui_sync_preview",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="vps_deploy:ui_sync_preview",
                next_action="Controleer of de UI dist bestaat en de host bridge SSH/rsync kan bereiken.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "vps_ui_sync_preview",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "preview" else _stringify(payload),
            source="vps_deploy:ui_sync_preview",
            approval_status="not_required_dry_run",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "vps_ui_sync_preview", "taint": "host_deploy_metadata_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Review de UI dry-run; vps_ui_sync_execute bouwt eerst lokaal en vereist exact Akkoord.",
        )

    def vps_ui_sync_execute(self, *, approval: str = "", remote_path: str = "", timeout_seconds: int = 120, build_first: bool = True) -> dict[str, Any]:
        if str(approval or "").strip() != "Akkoord":
            ziel_policy = ziel_guardrail_note()
            payload = {
                "remote_path": remote_path,
                "approval_required": True,
                "executed": False,
                "mutated": False,
                "remote_target": "/var/www/philip-wintrip.nl/html/Ouroboros/",
                "ui_artifact_source": "ouroboros_cockpit/dist",
                "secrets_returned": False,
                "ziel_policy": ziel_policy,
            }
            return _tool_result(
                "vps_ui_sync_execute",
                "blocked",
                result=payload,
                stdout=_stringify(payload),
                stderr="VPS UI sync execution requires exact Akkoord.",
                source="vps_deploy:ui_sync_execute",
                approval_status="pending_philip_akkoord",
                metadata_11d={"dimension_count": 11, "source_type": "vps_ui_sync_execute_gate", "taint": "host_mutation_gate", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
                next_action="Vraag Philip om exact Akkoord na review van vps_ui_sync_preview.",
            )
        try:
            from controller.vps_deploy_adapter import VPSDeployAdapter

            raw = VPSDeployAdapter().ui_sync_execute(
                approval=approval,
                remote_path=remote_path,
                timeout_seconds=max(10, min(int(timeout_seconds or 120), 900)),
                build_first=build_first,
            )
        except Exception as exc:
            return _tool_result(
                "vps_ui_sync_execute",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="vps_deploy:ui_sync_execute",
                approval_status="approved",
                next_action="Controleer UI build/npm en de host bridge/rsync fout zonder secrets te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "vps_ui_sync_execute",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source="vps_deploy:ui_sync_execute",
            approval_status="approved",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "vps_ui_sync_execute", "taint": "host_mutation_audit", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Controleer de VPS UI in de browser; alleen dist artifacts zijn naar de webroot gestuurd.",
        )

    def chroma_sync_status(self, *, timeout_seconds: int = 45) -> dict[str, Any]:
        try:
            from controller.chroma_sync_adapter import ChromaSyncAdapter

            raw = ChromaSyncAdapter().status(timeout_seconds=max(10, min(int(timeout_seconds or 45), 300)))
        except Exception as exc:
            return _tool_result(
                "chroma_sync_status",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="chroma_sync:status",
                next_action="Controleer Chroma sync config in .secrets/vps.env en host SSH bereikbaarheid.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "chroma_sync_status",
            "success" if status in {"ready", "online", "degraded"} else status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status in {"ready", "online", "degraded"} else _stringify(payload),
            source="chroma_sync:status",
            approval_status="not_required_status",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "chroma_sync_status", "taint": "memory_metadata_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Gebruik chroma_sync_preview om ontbrekende records te tellen; execute vereist exact Akkoord.",
        )

    def chroma_sync_preview(self, *, timeout_seconds: int = 120) -> dict[str, Any]:
        try:
            from controller.chroma_sync_adapter import ChromaSyncAdapter

            raw = ChromaSyncAdapter().preview(timeout_seconds=max(10, min(int(timeout_seconds or 120), 900)))
        except Exception as exc:
            return _tool_result(
                "chroma_sync_preview",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="chroma_sync:preview",
                next_action="Controleer lokale/VPS Chroma bereikbaarheid; preview hoort geen documenten terug te geven.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "chroma_sync_preview",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "preview" else _stringify(payload),
            source="chroma_sync:preview",
            approval_status="not_required_dry_run",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "chroma_sync_preview", "taint": "memory_metadata_only", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Review missing_on_local/missing_on_remote; chroma_sync_execute versmelt pas na exact Akkoord.",
        )

    def chroma_sync_execute(self, *, approval: str = "", timeout_seconds: int = 300) -> dict[str, Any]:
        if str(approval or "").strip() != "Akkoord":
            ziel_policy = ziel_guardrail_note()
            payload = {
                "approval_required": True,
                "executed": False,
                "mutated": False,
                "raw_documents_returned": False,
                "secrets_returned": False,
                "ziel_policy": ziel_policy,
            }
            return _tool_result(
                "chroma_sync_execute",
                "blocked",
                result=payload,
                stdout=_stringify(payload),
                stderr="Chroma merge execution requires exact Akkoord.",
                source="chroma_sync:execute",
                approval_status="pending_philip_akkoord",
                metadata_11d={"dimension_count": 11, "source_type": "chroma_sync_execute_gate", "taint": "memory_mutation_gate", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
                next_action="Vraag Philip om exact Akkoord na review van chroma_sync_preview.",
            )
        try:
            from controller.chroma_sync_adapter import ChromaSyncAdapter

            raw = ChromaSyncAdapter().execute(
                approval=approval,
                timeout_seconds=max(30, min(int(timeout_seconds or 300), 900)),
            )
        except Exception as exc:
            return _tool_result(
                "chroma_sync_execute",
                "error",
                stderr=_redact_operational_text(str(exc)),
                source="chroma_sync:execute",
                approval_status="approved",
                next_action="Controleer Chroma/SSH fout; raw documenten worden niet in tooloutput gezet.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        return _tool_result(
            "chroma_sync_execute",
            status,
            result=payload,
            stdout=_stringify(payload),
            stderr="" if status == "success" else _stringify(payload),
            source="chroma_sync:execute",
            approval_status="approved",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "chroma_sync_execute", "taint": "memory_mutation_audit", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Controleer na de merge beide Chroma statuspanelen; raw geheugeninhoud is niet geretourneerd.",
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
        try:
            from controller.google_workspace_adapter import GoogleWorkspaceAdapter

            raw = GoogleWorkspaceAdapter(live_api_enabled=True).send_gmail(
                to=to,
                subject=subject,
                body=body,
                approval=approval,
            )
        except Exception as exc:
            return _tool_result(
                "mail_send",
                "error",
                result={**preview["result"], "sent": False, "send_adapter_configured": False},
                stderr=_redact_operational_text(str(exc)),
                source="google_workspace:gmail_send",
                approval_status="approved",
                next_action="Controleer Google OAuth/scopes zonder tokenmateriaal te delen.",
            )
        payload = _sanitize_connector_payload(raw)
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
        raw_status = str(raw.get("status") or "error") if isinstance(raw, dict) else "error"
        status = "success" if raw_status == "success" else raw_status
        sent = bool(raw.get("executed")) if isinstance(raw, dict) else False
        return _tool_result(
            "mail_send",
            status,
            result={**payload, "sent": sent, "send_adapter_configured": True},
            stdout=_stringify({**payload, "sent": sent}),
            stderr="" if status == "success" else _stringify(payload),
            source="google_workspace:gmail_send",
            approval_status="approved",
            stored_to_memory=False,
            metadata_11d={"dimension_count": 11, "source_type": "gmail_send", "taint": "private_user_mutation", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
            next_action="Controleer het resultaat. Gmail-verzending kan niet automatisch worden teruggedraaid.",
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
        openclaw = openclaw_voice_status_payload()
        configured = bool(openclaw.get("configured"))
        available = bool(openclaw.get("available"))
        payload = {
            "status": "online" if available else ("configured" if configured else "not_configured"),
            "input": {"microphone": configured, "speech_to_text": configured},
            "output": {"text_to_speech": configured},
            "openclaw": openclaw,
            "pocket_voice": "available_for_text_chat",
            "route": "openclaw_voice_gateway" if configured else "status_only",
            "fake_success": False,
        }
        return _tool_result(
            "voice_chat_status",
            "success",
            result=payload,
            stdout=_stringify(payload),
            source="voice:status",
            next_action=str(openclaw.get("next_action") or "Start OpenClaw Voice and connect from the cockpit."),
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
        is_trainable_ingest = approval_status == "approved" and tool_name == "training_ingest"
        result_metadata = {
            **base_metadata,
            "learnable": is_trainable_ingest,
            "audit_only": not is_trainable_ingest,
            "geometry_11d": geometry,
        }
        storage_metadata = _flatten_metadata(
            {
                **base_metadata,
                **(extra_metadata or {}),
                "type": "agent_learning_action_11d",
                "tool_name": tool_name,
                "approval_status": approval_status,
                "learnable": is_trainable_ingest,
                "audit_only": not is_trainable_ingest,
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
        if tool in {"browser_research", "chatgpt_browser_ask", "brave_search", "ns_travel_advice", "ov9292_travel_advice", "world_grok_ask", "mail_read_recent", "mail_send", "gmail_status", "gmail_search", "google_drive_status", "google_drive_list", "github_status", "github_repo", "github_search_repositories", "social_post_publish", "codex_job_start", "resolve_or_build_function"}:
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


def _connector_gate_for_tool(tool_name: str) -> dict[str, Any]:
    try:
        from controller.connector_catalog import is_tool_enabled

        gate = is_tool_enabled(tool_name)
        return gate if isinstance(gate, dict) else {"enabled": True, "tool_name": tool_name, "fake_success": False}
    except Exception:
        return {
            "enabled": True,
            "tool_name": tool_name,
            "reason": "Connector catalog unavailable; keeping existing tool behavior.",
            "fake_success": False,
        }


def _connector_disabled_result(tool_name: str, gate: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "tool_name": tool_name,
        "connector_id": gate.get("connector_id", ""),
        "connector_name": gate.get("connector_name", ""),
        "enabled": False,
        "reason": gate.get("reason") or "Connector disabled in cockpit.",
        "executed": False,
        "secrets_returned": False,
        "fake_success": False,
    }
    return _tool_result(
        tool_name,
        "blocked",
        result=payload,
        stdout=json.dumps(payload, ensure_ascii=False, indent=2),
        stderr=str(payload["reason"]),
        source="connector_catalog",
        approval_status="connector_disabled",
        stored_to_memory=False,
        metadata_11d={"dimension_count": 11, "source_type": "connector_catalog_gate", "taint": "connector_disabled"},
        next_action=f"Zet connector {payload['connector_name'] or payload['connector_id']} aan in de Cockpit Connectors-tab met exact Akkoord.",
    )


def _private_connector_read_blocked_result(
    tool_name: str,
    *,
    payload: Mapping[str, Any],
    source: str,
    source_type: str,
    stderr: str,
    next_action: str,
) -> dict[str, Any]:
    ziel_policy = ziel_guardrail_note()
    blocked_payload = _sanitize_connector_payload(
        {
            **dict(payload),
            "approval_required": True,
            "read_only": True,
            "executed": False,
            "secrets_returned": False,
            "ziel_policy": ziel_policy,
        }
    )
    return _tool_result(
        tool_name,
        "blocked",
        result=blocked_payload,
        stdout=_stringify(blocked_payload),
        stderr=stderr,
        source=source,
        approval_status="pending_philip_akkoord",
        metadata_11d={"dimension_count": 11, "source_type": source_type, "taint": "private_user_data", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
        next_action=next_action,
    )


def _private_connector_read_result(
    tool_name: str,
    raw: Any,
    *,
    source: str,
    source_type: str,
    limit: int,
    next_action: str,
) -> dict[str, Any]:
    raw_payload = raw if isinstance(raw, dict) else {"status": "error", "response": raw, "fake_success": False}
    payload = _sanitize_connector_payload(raw_payload)
    if isinstance(payload, dict):
        _limit_connector_payload(payload, max(1, int(limit or 1)))
        payload["read_only"] = True
        payload["secrets_returned"] = False
        ziel_policy = ziel_guardrail_note()
        payload["ziel_policy"] = ziel_policy
    else:
        ziel_policy = ziel_guardrail_note()
    raw_status = str(raw_payload.get("status") or "error")
    status = "success" if raw_status == "success" else raw_status
    stdout = _stringify(payload)
    return _tool_result(
        tool_name,
        status,
        result=payload,
        stdout=stdout,
        stderr="" if status == "success" else stdout,
        source=source,
        approval_status="approved",
        stored_to_memory=False,
        metadata_11d={"dimension_count": 11, "source_type": source_type, "taint": "private_user_data", "ziel_policy_hash": ziel_policy.get("short_hash", "")},
        next_action=next_action,
    )


def _limit_connector_payload(payload: dict[str, Any], limit: int) -> None:
    for key in ("items", "messages", "records_11d", "findings"):
        value = payload.get(key)
        if isinstance(value, list):
            payload[f"{key}_total_count"] = len(value)
            payload[key] = value[:limit]
            payload[f"{key}_returned_count"] = len(payload[key])


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


def _ns_api_enabled() -> bool:
    mode = os.getenv("WINTRIP_NS_API_MODE", "").strip().lower()
    if mode in {"api", "on", "true", "1"}:
        return True
    return _bool_arg(os.getenv("WINTRIP_TRAVEL_USE_NS_API"), default=False)


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


def _ov9292_planner_links(
    from_place: str,
    to_place: str,
    *,
    date_time: str = "",
    search_for_arrival: bool = False,
    query: str = "",
) -> list[str]:
    base_params: dict[str, str] = {}
    if from_place:
        base_params["from"] = from_place
    if to_place:
        base_params["to"] = to_place
    if date_time:
        base_params["dateTime"] = date_time[:16]
        base_params["timeType"] = "arrival" if search_for_arrival else "departure"
    if query:
        base_params["query"] = " ".join(str(query or "").split())[:400]
    links = ["https://9292.nl/" + (("?" + urlencode(base_params)) if base_params else "")]
    planner_params = {}
    if from_place:
        planner_params["vertrek"] = from_place
    if to_place:
        planner_params["aankomst"] = to_place
    if date_time:
        planner_params["tijd"] = date_time[:16]
        planner_params["type"] = "aankomst" if search_for_arrival else "vertrek"
    if planner_params:
        links.append("https://9292.nl/reisadvies?" + urlencode(planner_params))
    if query:
        links.append("https://9292.nl/zoeken?" + urlencode({"q": " ".join(str(query or "").split())[:400]}))
    return _unique_texts(links)


def _official_travel_browser_lookup(
    *,
    provider: str,
    planner_url: str,
    from_place: str,
    to_place: str,
    date_time: str,
    search_for_arrival: bool,
    enabled: bool | None,
) -> dict[str, Any]:
    if not _travel_browser_lookup_enabled(enabled):
        return {
            "status": "skipped",
            "enabled": False,
            "authoritative": False,
            "official_visible_text": False,
            "browser_action_performed": False,
            "reason": "browser lookup disabled",
            "planner_url": planner_url,
            "secrets_returned": False,
            "fake_success": False,
        }
    try:
        from controller.browser_research import read_visible_text

        raw = read_visible_text(planner_url)
    except Exception as exc:
        return {
            "status": "error",
            "enabled": True,
            "authoritative": False,
            "official_visible_text": False,
            "browser_action_performed": False,
            "reason": str(exc)[:500],
            "planner_url": planner_url,
            "secrets_returned": False,
            "fake_success": False,
        }

    if not isinstance(raw, dict):
        raw = {"status": "error", "reason": "browser lookup returned non-dict"}
    text = str(raw.get("scrubbed_text") or raw.get("visible_text") or "")
    snippets = _travel_visible_snippets(text, from_place=from_place, to_place=to_place)
    time_source = "\n".join(snippets) if snippets else text
    visible_times = _extract_time_values(time_source)
    raw_status = str(raw.get("status") or "unknown")
    browser_performed = bool(raw.get("browser_action_performed"))
    official_visible = raw_status == "success" and browser_performed and bool(text.strip())
    place_match = _contains_route_places(text, from_place=from_place, to_place=to_place)
    authoritative = bool(official_visible and snippets and len(visible_times) >= 2 and place_match)
    return {
        "status": "success" if authoritative else raw_status,
        "enabled": True,
        "provider": provider,
        "planner_url": planner_url,
        "date_time": date_time,
        "search_for_arrival": bool(search_for_arrival),
        "authoritative": authoritative,
        "official_visible_text": official_visible,
        "browser_action_performed": browser_performed,
        "raw_status": raw_status,
        "reason": str(raw.get("reason") or ""),
        "next_action": str(raw.get("next_action") or ""),
        "title": str(raw.get("title") or ""),
        "source_url": str(raw.get("source_url") or raw.get("url") or planner_url),
        "visible_times": visible_times,
        "visible_snippets": snippets,
        "visible_text_excerpt": _compact_visible_excerpt(text),
        "approval_status": str(raw.get("approval_status") or "not_required_readonly"),
        "secrets_returned": False,
        "fake_success": False,
    }


def _official_planner_tool_result(
    *,
    tool_name: str,
    payload: dict[str, Any],
    browser: dict[str, Any],
    planner_links: list[str],
    source: str,
    fallback_intro: str,
    metadata_source_type: str,
) -> dict[str, Any]:
    authoritative = bool(browser.get("authoritative"))
    payload = {
        **payload,
        "authoritative": authoritative,
        "official_visible_text": bool(browser.get("official_visible_text")),
        "visible_planner_authoritative": authoritative,
        "visible_times": list(browser.get("visible_times") or []),
        "visible_snippets": list(browser.get("visible_snippets") or []),
        "secrets_returned": False,
        "fake_success": False,
    }
    lines = [fallback_intro]
    if authoritative:
        lines.append("Zichtbare officiële plannerdata gevonden. Exacte tijden mogen alleen uit deze snippets komen:")
        lines.extend(f"- {snippet}" for snippet in payload["visible_snippets"][:5])
    else:
        reason = str(browser.get("reason") or browser.get("raw_status") or browser.get("status") or "geen routekaart zichtbaar").strip()
        lines.append(f"Er zijn geen officiële treintijden/OV-tijden zichtbaar opgehaald ({reason}); ik noem daarom geen exacte tijden.")
    lines.append("Officiële plannerlinks:")
    lines.extend(f"- {link}" for link in planner_links)
    status = "success" if authoritative else "preview"
    taint = "official_visible_planner" if authoritative else "official_link_fallback"
    next_action = (
        "Gebruik alleen de zichtbare officiële snippets voor tijden; controleer de planner bij twijfel."
        if authoritative
        else "Open de officiële plannerlink handmatig of zorg dat Playwright/browser lookup de routekaart zichtbaar kan lezen."
    )
    return _tool_result(
        tool_name,
        status,
        result=payload,
        stdout="\n".join(lines),
        source=source,
        approval_status="not_required_readonly",
        metadata_11d={"dimension_count": 11, "source_type": metadata_source_type, "taint": taint},
        next_action=next_action,
    )


def _travel_browser_lookup_enabled(value: bool | None) -> bool:
    if value is not None:
        return bool(value)
    return _bool_arg(os.getenv("WINTRIP_TRAVEL_BROWSER_LOOKUP"), default=True)


def _travel_visible_snippets(text: str, *, from_place: str, to_place: str) -> list[str]:
    route_terms = (
        "reis",
        "advies",
        "vertrek",
        "aankomst",
        "overstap",
        "spoor",
        "perron",
        "platform",
        "intercity",
        "sprinter",
        "trein",
        "bus",
        "tram",
        "metro",
        "lopen",
        "walk",
        "departure",
        "arrival",
    )
    lines = [" ".join(line.split()) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    snippets: list[str] = []
    for index, line in enumerate(lines):
        if not _extract_time_values(line):
            continue
        window = " ".join(lines[max(0, index - 2) : min(len(lines), index + 3)])
        lowered = window.lower()
        if any(term in lowered for term in route_terms) or _contains_route_places(window, from_place=from_place, to_place=to_place):
            snippets.append(window[:500])
        if len(snippets) >= 5:
            break
    return _unique_texts(snippets)


def _extract_time_values(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"\b([01]?\d|2[0-3])[:.](\d{2})\b", str(text or "")):
        values.append(f"{int(match.group(1)):02d}:{match.group(2)}")
    return _unique_texts(values)


def _contains_route_places(text: str, *, from_place: str, to_place: str) -> bool:
    normalized = _normalize_place_text(text)
    return _place_mentioned(normalized, from_place) and _place_mentioned(normalized, to_place)


def _place_mentioned(normalized_text: str, place: str) -> bool:
    words = [word for word in _normalize_place_text(place).split() if len(word) >= 3 and word not in {"station", "centraal"}]
    if not words:
        return True
    return any(word in normalized_text for word in words[:3])


def _normalize_place_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _compact_visible_excerpt(text: str) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:1800]


def _connector_services_from_prompt(prompt: str, provided: list[Any]) -> list[str]:
    lowered = str(prompt or "").lower()
    services = [str(item).strip().lower().replace(" ", "_") for item in provided if str(item or "").strip()]
    if "gmail" in lowered or "google mail" in lowered or re.search(r"\b(mail|email|e-mail|inbox)\b", lowered):
        services.append("gmail")
    if "google drive" in lowered or "gdrive" in lowered or re.search(r"\bdrive\b", lowered):
        services.append("google_drive")
    if "github" in lowered or "git hub" in lowered:
        services.append("github")
    if any(marker in lowered for marker in ("vps", "ssh", "rsync", "scp", "deploy", "server login", "remote server")):
        services.append("vps")
    return _unique_texts(services)


def _connector_prompt_mutating(prompt: str) -> bool:
    lowered = str(prompt or "").lower()
    return bool(
        re.search(
            r"\b(send|verstuur|reply|antwoord|archive|label|upload|write|schrijf|create|maak|delete|verwijder|deploy|sync|synchroniseer|login|log\s+in|push|merge|commit|ssh|scp|rsync)\b",
            lowered,
        )
    )


def _connector_blocked_tools(services: list[str], action_type: str) -> list[str]:
    mapping = {
        "gmail": "gmail_connector",
        "google_drive": "google_drive_connector",
        "github": "github_connector",
        "vps": "vps_host_action",
    }
    blocked = [mapping.get(service, f"{service}_connector") for service in services]
    if not blocked:
        blocked = ["private_connector"]
    if "mutating" in str(action_type or ""):
        blocked.append("mutating_connector_action")
    return _unique_texts(blocked)


def _unique_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


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
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b"),
    )
    for pattern in patterns:
        redacted = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]" if match.groups() else "[REDACTED]", redacted)
    return redacted


def _sanitize_connector_payload(value: Any) -> Any:
    safe_key_names = {
        "token_type",
        "has_refresh_token",
        "tokens_returned",
        "secrets_returned",
        "required_key_env",
        "masked",
        "store_path",
        "writable",
        "configured",
        "source",
        "source_type",
        "fake_success",
    }
    sensitive_names = {"access_token", "refresh_token", "client_secret", "api_key", "authorization", "password", "passwd", "secret", "token", "bearer", "private_key", "ssh_key"}
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered == "token" and isinstance(item, dict):
                output[key_text] = _sanitize_connector_payload(item)
            elif lowered not in safe_key_names and (lowered in sensitive_names or lowered.endswith("_token") or lowered.endswith("_secret") or lowered.endswith("_key")):
                output[key_text] = "[REDACTED]" if item not in (None, "", False) else item
            else:
                output[key_text] = _sanitize_connector_payload(item)
        return output
    if isinstance(value, list):
        return [_sanitize_connector_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_connector_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_operational_text(value)
    return value


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


def _bool_arg(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "ja", "aan"}:
        return True
    if text in {"0", "false", "no", "n", "off", "nee", "uit"}:
        return False
    return default


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
