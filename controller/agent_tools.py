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
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable
from urllib.parse import urlparse

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
    "browser_research",
    "chatgpt_browser_ask",
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
            elif tool_name == "browser_research":
                result = self.browser_research(
                    str(args.get("query") or args.get("prompt") or ""),
                    str(args.get("approval") or ""),
                    _int(args.get("limit"), default=3),
                )
            elif tool_name == "chatgpt_browser_ask":
                result = self.chatgpt_browser_ask(
                    str(args.get("question") or args.get("prompt") or ""),
                    str(args.get("approval") or ""),
                )
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

        # Roo-tools are high priority for the new cockpit
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "roo_read_file",
                    "description": "Leest de inhoud van een bestand in de workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Pad relatief aan /workspace."},
                            "offset": {"type": "integer", "description": "Start byte."},
                            "limit": {"type": "integer", "description": "Maximum bytes om te lezen."}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "roo_write_file",
                    "description": "Schrijft of overschrijft een bestand in de workspace. VEREIST PHILIP AKKOORD.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Pad relatief aan /workspace."},
                            "content": {"type": "string", "description": "De volledige nieuwe inhoud."},
                            "approval": {"type": "string", "description": "Moet 'Akkoord' bevatten voor echte schrijfactie."}
                        },
                        "required": ["path", "content", "approval"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "roo_execute_command",
                    "description": "Voert een veilig shell-commando uit in de /workspace sandbox. VEREIST PHILIP AKKOORD.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Het commando, bijv. 'ls -la' of 'pytest'."},
                            "approval": {"type": "string", "description": "Moet 'Akkoord' bevatten."}
                        },
                        "required": ["command", "approval"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "roo_attempt_completion",
                    "description": "Signaleert dat de taak voltooid is of een mijlpaal is bereikt.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "result": {"type": "string", "description": "Samenvatting van wat er gedaan is."},
                            "command": {"type": "string", "description": "Optioneel commando om resultaat te verifiëren."}
                        },
                        "required": ["result"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_search",
                    "description": "Zoekt in de 11D Hippocampus naar relevante eerdere kennis en code.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "De zoekterm."},
                            "limit": {"type": "integer", "description": "Aantal resultaten (max 12)."}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        if provider == "anthropic":
            return [self._to_anthropic_schema(s) for s in schemas]

        return schemas

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

                raw = run_browser_research(query=query, approval=approval)
        except Exception as exc:
            return _tool_result(
                "browser_research",
                "error",
                stderr=str(exc),
                source="browser_research",
                approval_status="approved",
                next_action="Retry later or use manual browser_text with scrub_browser_content.",
            )

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
            result={"query": query, "response": raw, "stored": False},
            stdout=stdout,
            stderr="" if status == "success" else stdout,
            source="browser_research",
            approval_status=(raw.get("approval_status") if isinstance(raw, dict) else "approved") or "approved",
            stored_to_memory=False,
            metadata_11d={},
            next_action="Review diff_view/scrubbed_text; use training_ingest with Akkoord for 11D storage.",
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
        if not SAFE_TEST_SELECTOR_RE.match(selector):
            return _tool_result(
                "run_tests",
                "error",
                stderr="Test selector contains blocked characters.",
                source="python_unittest",
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
        if tool in {"memory_search", "prompt_understanding", "self_training_plan", "inspect_hippocampus"}:
            return {"level": "high", "label": "High: local memory and planning first", "memory_first": True}
        if tool in {"scrub_browser_content", "training_ingest", "safe_shell", "run_tests"}:
            return {"level": "medium", "label": "Medium: approval-gated local action", "memory_first": True}
        if str(tool or "").startswith("roo_"):
            return {"level": "medium", "label": "Medium: Roo adapter under workspace/approval gates", "memory_first": True}
        if tool in {"browser_research", "chatgpt_browser_ask"}:
            return {"level": "guarded", "label": "Guarded: external/browser perimeter", "memory_first": True}
        return {"level": "unknown", "label": "No registered tool result yet", "memory_first": False}


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

    candidate_actions: list[dict[str, Any]] = []
    if wants_shell:
        candidate_actions.append({"tool": "run_tests", "approval_required": True})
    if wants_chatgpt:
        candidate_actions.append({"tool": "chatgpt_browser_ask", "approval_required": True})
    if wants_training:
        candidate_actions.append({"tool": "training_ingest", "approval_required": True})
    if asks_current:
        candidate_actions.append({"tool": "browser_research", "approval_required": True})

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
        import chromadb
    except Exception as exc:
        raise RuntimeError(f"chromadb is not available: {exc}") from exc
    persist_dir = os.getenv("WINTRIP_DB_PATH", "wintrip_brain")
    collection_name = os.getenv("WINTRIP_TRAINING_COLLECTION", "wintrip_training_11d")
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(name=collection_name)


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
