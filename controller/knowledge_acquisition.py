"""Traceable knowledge acquisition for Ouroboros curricula.

This module turns the local OUROBOROS_KENNIS_LIJST.md file into a bounded
training plan. It can distill local Ollama/Gemma knowledge per topic and, when
approved, read one browser page per topic through the existing Playwright
perimeter. Every stored record is marked with its real source path/action.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:
    requests = None  # type: ignore[assignment]

from controller.safe_shell import workspace_root
from controller.training_curriculum import classify_record


APPROVAL_PHRASE = "Akkoord"
DEFAULT_KNOWLEDGE_LIST_PATH = "/home/pwintri2/Downloads/OUROBOROS_KENNIS_LIJST.md"
DEFAULT_GEMMA_MODEL = os.getenv("WINTRIP_KNOWLEDGE_MODEL") or os.getenv("WINTRIP_GEMMA_GUARD_MODEL") or "gemma4:latest"
MAX_TOPIC_TEXT = 1200
MAX_RECORD_CHARS = 16_000

SECTION_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


def knowledge_list_path() -> Path:
    configured = os.getenv("WINTRIP_KNOWLEDGE_LIST_PATH")
    return Path(configured or DEFAULT_KNOWLEDGE_LIST_PATH).expanduser().resolve()


def knowledge_state_path() -> Path:
    return (workspace_root() / ".secrets" / "knowledge_acquisition.json").resolve()


def get_knowledge_acquisition_status() -> dict[str, Any]:
    state = _load_state()
    parsed = parse_knowledge_list()
    topics = parsed.get("topics", [])
    records = state.get("records") or []
    gemma_done = _completed_topics(records, "gemma_distillation")
    browser_done = _completed_topics(records, "browser_research_call")
    brave_done = _completed_topics(records, "brave_llm_context")
    last_records = list(records)[-12:]
    try:
        from controller.brave_search import brave_search_status

        brave_status = brave_search_status()
    except Exception as exc:
        brave_status = {"status": "unavailable", "configured": False, "reason": str(exc), "fake_success": False}
    return {
        "status": "ready" if parsed.get("status") == "success" else "missing",
        "knowledge_list_path": str(knowledge_list_path()),
        "state_path": str(knowledge_state_path()),
        "topic_count": len(topics),
        "section_count": len(parsed.get("sections") or []),
        "gemma_model": state.get("gemma_model", DEFAULT_GEMMA_MODEL),
        "gemma_completed": len(gemma_done),
        "browser_completed": len(browser_done),
        "brave_completed": len(brave_done),
        "brave_search": brave_status,
        "total_records": len(records),
        "last_indexed_at": state.get("last_indexed_at"),
        "last_tick_at": state.get("last_tick_at"),
        "last_error": state.get("last_error", ""),
        "next_gemma_topics": _next_topics(topics, gemma_done, limit=5),
        "next_browser_topics": _next_topics(topics, browser_done, limit=5),
        "next_brave_topics": _next_topics(topics, brave_done, limit=5),
        "recent_records": last_records,
        "curriculum_counts": _curriculum_counts(records),
        "fake_success": False,
    }


def parse_knowledge_list(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path).expanduser().resolve() if path else knowledge_list_path()
    if not source.exists():
        return {
            "status": "missing",
            "reason": f"Knowledge list not found: {source}",
            "path": str(source),
            "sections": [],
            "topics": [],
            "fake_success": False,
        }

    text = source.read_text(encoding="utf-8", errors="replace")
    sections: list[dict[str, Any]] = []
    topics: list[dict[str, Any]] = []
    section_stack: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        heading = SECTION_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = _clean_inline(heading.group(2))
            section_id = _slug(title)
            section = {
                "id": section_id,
                "level": level,
                "title": title,
                "line": line_number,
                "path": "",
                "summary": "",
                "bullet_count": 0,
            }
            while section_stack and int(section_stack[-1]["level"]) >= level:
                section_stack.pop()
            section_stack.append(section)
            section["path"] = " > ".join(str(item["title"]) for item in section_stack)
            sections.append(section)
            current_section = section
            if level >= 3:
                topics.append(_topic_from_heading(section, len(topics)))
            continue

        bullet = BULLET_RE.match(line)
        if bullet and current_section:
            bullet_text = _clean_inline(bullet.group(1))
            if bullet_text:
                current_section["bullet_count"] = int(current_section.get("bullet_count") or 0) + 1
                topics.append(
                    {
                        "id": f"{current_section['id']}__{_slug(bullet_text)[:80]}",
                        "index": len(topics),
                        "title": bullet_text[:220],
                        "query": _topic_query(current_section.get("path", ""), bullet_text),
                        "section": current_section.get("title", ""),
                        "section_path": current_section.get("path", ""),
                        "source_path": str(source),
                        "line": line_number,
                        "kind": "bullet",
                        "curriculum": classify_record(bullet_text, {"source": str(source)}),
                    }
                )
            continue

        stripped = line.strip()
        if current_section and stripped and not stripped.startswith("```"):
            summary = str(current_section.get("summary") or "")
            if len(summary) < 320:
                current_section["summary"] = (summary + " " + _clean_inline(stripped)).strip()[:320]

    deduped_topics = _dedupe_topics(topics)
    return {
        "status": "success",
        "path": str(source),
        "char_count": len(text),
        "sections": sections,
        "topics": deduped_topics,
        "topic_count": len(deduped_topics),
        "fake_success": False,
    }


def index_knowledge_list(approval: str = "", path: str | None = None) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    parsed = parse_knowledge_list(path)
    state = _load_state()
    state["knowledge_list_path"] = parsed.get("path")
    state["last_indexed_at"] = _now_iso()
    state["topic_count"] = len(parsed.get("topics") or [])
    state["section_count"] = len(parsed.get("sections") or [])
    state["last_error"] = "" if parsed.get("status") == "success" else parsed.get("reason", "")
    _save_state(state)
    return {
        "status": parsed.get("status"),
        "knowledge_list_path": parsed.get("path"),
        "topic_count": state["topic_count"],
        "section_count": state["section_count"],
        "next_topics": (parsed.get("topics") or [])[:10],
        "state_path": str(knowledge_state_path()),
        "fake_success": False,
    }


def run_knowledge_tick(
    approval: str = "",
    mode: str = "both",
    max_topics: int = 3,
    start_index: int | None = None,
    model: str = DEFAULT_GEMMA_MODEL,
) -> dict[str, Any]:
    """Run a bounded knowledge acquisition tick.

    mode can be gemma, browser, brave, both, gemma_brave or all. The browser
    path uses the existing browser_research function, which reads exactly one
    page per topic. The Brave path uses Brave LLM Context for machine-readable
    grounding and stores it as approved 11D training context after Akkoord.
    """
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}

    clean_mode = (mode or "both").strip().lower()
    valid_modes = {"both", "gemma", "browser", "brave", "gemma_brave", "all"}
    if clean_mode not in valid_modes:
        return {"status": "error", "reason": f"mode must be one of: {', '.join(sorted(valid_modes))}", "fake_success": False}

    parsed = parse_knowledge_list()
    if parsed.get("status") != "success":
        return parsed

    topics = list(parsed.get("topics") or [])
    bounded_max = max(1, min(int(max_topics or 1), 10))
    state = _load_state()
    records = state.setdefault("records", [])
    errors: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []

    source_types = []
    if clean_mode in {"both", "gemma", "gemma_brave", "all"}:
        source_types.append("gemma_distillation")
    if clean_mode in {"both", "browser", "all"}:
        source_types.append("browser_research_call")
    if clean_mode in {"brave", "gemma_brave", "all"}:
        source_types.append("brave_llm_context")

    parallelism: dict[str, int] = {}
    selected_topics: dict[str, list[dict[str, Any]]] = {}
    for source_type in source_types:
        completed = _completed_topics(records, source_type)
        selected = _select_topics(
            topics,
            completed,
            bounded_max,
            start_index,
            records=records,
            source_type=source_type,
        )
        selected_topics[source_type] = _topic_selection_summary(selected)
        parallelism[source_type] = _parallelism_for_source(source_type, len(selected))
        for topic, result, exception in _acquire_topics(
            topics=selected,
            source_type=source_type,
            approval=approval,
            model=model,
            workers=parallelism[source_type],
        ):
            try:
                if exception is not None:
                    raise exception

                if result.get("status") not in {"success", "preview"}:
                    errors.append(
                        {
                            "topic_id": topic.get("id"),
                            "source_type": source_type,
                            "status": result.get("status", "error"),
                            "reason": result.get("reason", result.get("detail", "")),
                        }
                    )
                    continue

                document = str(result.get("document") or result.get("scrubbed_text") or "")[:MAX_RECORD_CHARS]
                if not document.strip():
                    errors.append(
                        {
                            "topic_id": topic.get("id"),
                            "source_type": source_type,
                            "status": "error",
                            "reason": "Empty acquired document.",
                        }
                    )
                    continue

                metadata = _record_metadata(topic=topic, source_type=source_type, result=result, model=model)
                stored = store_knowledge_record(document, metadata)
                record = {
                    "timestamp": metadata["ingested_at"],
                    "topic_id": topic.get("id"),
                    "topic_title": topic.get("title"),
                    "source_type": source_type,
                    "status": stored.get("status"),
                    "item_id": stored.get("item_id"),
                    "stored": stored.get("stored", False),
                    "curriculum_primary": metadata.get("curriculum_primary"),
                    "source": metadata.get("source"),
                    "browser_action_performed": bool(result.get("browser_action_performed", False)),
                    "chars": len(document),
                }
                records.append(record)
                created.append(record)
            except Exception as exc:
                errors.append(
                    {
                        "topic_id": topic.get("id"),
                        "source_type": source_type,
                        "status": "error",
                        "reason": str(exc),
                    }
                )

    state["records"] = records[-1000:]
    state["gemma_model"] = model
    state["last_tick_at"] = _now_iso()
    state["last_error"] = "; ".join(item.get("reason", "") for item in errors[-3:])
    state["knowledge_list_path"] = parsed.get("path")
    state["topic_count"] = len(topics)
    _save_state(state)
    status = "success" if created else ("partial" if errors else "noop")
    return {
        "status": status,
        "mode": clean_mode,
        "created_count": len(created),
        "error_count": len(errors),
        "parallelism": parallelism,
        "selection_strategy": "curriculum_gap_first" if start_index is None else "start_index_linear",
        "selected_topics": selected_topics,
        "created": created,
        "errors": errors,
        "state": get_knowledge_acquisition_status(),
        "fake_success": False,
    }


def _acquire_topics(
    topics: list[dict[str, Any]],
    source_type: str,
    approval: str,
    model: str,
    workers: int,
) -> list[tuple[dict[str, Any], dict[str, Any], Exception | None]]:
    if not topics:
        return []

    if source_type in {"gemma_distillation", "brave_llm_context"} and workers > 1:
        ordered: list[tuple[dict[str, Any], dict[str, Any], Exception | None] | None] = [None] * len(topics)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="knowledge-gemma") as executor:
            futures = {
                executor.submit(_acquire_one_topic, topic, source_type, approval, model): index
                for index, topic in enumerate(topics)
            }
            for future in as_completed(futures):
                index = futures[future]
                topic = topics[index]
                try:
                    ordered[index] = (topic, future.result(), None)
                except Exception as exc:
                    ordered[index] = (topic, {}, exc)
        return [item for item in ordered if item is not None]

    acquired: list[tuple[dict[str, Any], dict[str, Any], Exception | None]] = []
    for topic in topics:
        try:
            result = _acquire_one_topic(topic, source_type, approval, model)
            acquired.append((topic, result, None))
        except Exception as exc:
            acquired.append((topic, {}, exc))
    return acquired


def _acquire_one_topic(topic: dict[str, Any], source_type: str, approval: str, model: str) -> dict[str, Any]:
    if source_type == "gemma_distillation":
        return distill_gemma_topic(topic, model=model)
    if source_type == "brave_llm_context":
        return brave_research_topic(topic, approval=approval)
    return browser_research_topic(topic, approval=approval)


def _parallelism_for_source(source_type: str, selected_count: int) -> int:
    if source_type not in {"gemma_distillation", "brave_llm_context"} or selected_count <= 1:
        return 1
    env_name = "WINTRIP_BRAVE_KNOWLEDGE_PARALLELISM" if source_type == "brave_llm_context" else "WINTRIP_KNOWLEDGE_PARALLELISM"
    raw = os.getenv(env_name, "6" if source_type == "brave_llm_context" else "2")
    try:
        configured = int(raw)
    except (TypeError, ValueError):
        configured = 6 if source_type == "brave_llm_context" else 2
    maximum = 50 if source_type == "brave_llm_context" else 4
    return max(1, min(configured, selected_count, maximum))


def distill_gemma_topic(topic: dict[str, Any], model: str = DEFAULT_GEMMA_MODEL) -> dict[str, Any]:
    """Ask local Ollama/Gemma for a compact teachable distillation of one topic."""
    from controller.ollama_client import OllamaClient

    title = str(topic.get("title") or "")[:MAX_TOPIC_TEXT]
    section = str(topic.get("section_path") or topic.get("section") or "")[:MAX_TOPIC_TEXT]
    prompt = (
        "Je distilleert lokale trainingskennis voor Ouroboros. "
        "Geef compacte, feitelijke, Nederlandstalige kennis zonder claims over actuele data die je niet zeker weet. "
        "Structuur: kernbegrippen, praktische checks/commando's waar passend, risico's/approval gates, "
        "en hoe dit past in de 11D-pocket/curriculum.\n\n"
        f"Curriculumsectie: {section}\n"
        f"Onderwerp: {title}\n\n"
        "Maak er een bruikbare training memory van voor een lokaal technisch assistent-model."
    )
    started = time.time()
    client = OllamaClient(model=model)
    system = (
        "Je bent een lokale kennisdistillatie-agent voor WintripAI/Ouroboros. "
        "Je werkt offline/lokaal, schrijft compact en labelt onzekerheid eerlijk."
    )
    token_budget = max(80, min(int(os.getenv("WINTRIP_GEMMA_DISTILL_TOKENS", "360")), 900))
    response = _ollama_generate(
        base_url=client.base_url,
        model=model,
        prompt=prompt,
        system=system,
        num_predict=token_budget,
        timeout=max(20, min(int(os.getenv("WINTRIP_GEMMA_DISTILL_TIMEOUT", "75")), 180)),
    )
    duration = round(time.time() - started, 3)
    status = "error" if str(response).startswith("LOKALE OLLAMA ERROR") else "success"
    return {
        "status": status,
        "document": _limit_text(response, MAX_RECORD_CHARS),
        "model": model,
        "duration_seconds": duration,
        "source": f"ollama:{model}",
        "source_url": "",
        "fake_success": False,
        "reason": response if status == "error" else "",
    }


def _ollama_generate(
    base_url: str,
    model: str,
    prompt: str,
    system: str,
    num_predict: int,
    timeout: int,
) -> str:
    """Use Ollama generate with a bounded token budget for predictable ticks."""
    root = str(base_url or "http://localhost:11434").rstrip("/")
    if root.endswith("/api"):
        root = root[:-4]
    if requests is None:
        return f"LOKALE OLLAMA ERROR ({model}): requests module niet beschikbaar"
    try:
        response = requests.post(
            f"{root}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": 0.15,
                    "num_predict": num_predict,
                    "top_p": 0.9,
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return str(response.json().get("response") or "").strip()
    except Exception as exc:
        return f"LOKALE OLLAMA ERROR ({model}): {exc}"


def browser_research_topic(topic: dict[str, Any], approval: str = "") -> dict[str, Any]:
    """Read one browser page for a topic via the existing browser perimeter."""
    from controller.browser_research import browser_research

    query = str(topic.get("query") or topic.get("title") or "")[:500]
    result = browser_research(query=query, approval=approval)
    scrubbed = str(result.get("scrubbed_text") or "")
    result["document"] = _limit_text(
        "\n".join(
            part
            for part in [
                f"Browser research query: {query}",
                f"Source URL: {result.get('source_url') or result.get('url') or result.get('target_url') or ''}",
                scrubbed,
            ]
            if part
        ),
        MAX_RECORD_CHARS,
    )
    return result


def brave_research_topic(topic: dict[str, Any], approval: str = "") -> dict[str, Any]:
    """Fetch machine-readable Brave LLM Context for one curriculum topic."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "document": "", "fake_success": False}
    from controller.brave_search import brave_training_document

    query = str(topic.get("query") or topic.get("title") or "")[:400]
    result = brave_training_document(
        query,
        count=max(1, min(int(os.getenv("WINTRIP_BRAVE_CONTEXT_COUNT", "20") or 20), 50)),
        maximum_number_of_urls=max(1, min(int(os.getenv("WINTRIP_BRAVE_CONTEXT_URLS", "8") or 8), 50)),
        maximum_number_of_tokens=max(1024, min(int(os.getenv("WINTRIP_BRAVE_CONTEXT_TOKENS", "8192") or 8192), 32768)),
    )
    if result.get("status") == "success":
        result["browser_action_performed"] = False
        result["bulk_scraping"] = False
        result["taint"] = "untrusted_web:brave_llm_context"
        result["source_url"] = ",".join(list(result.get("source_urls") or [])[:8])
    return result


def store_knowledge_record(document: str, metadata: dict[str, Any]) -> dict[str, Any]:
    clean_document = _limit_text(document, MAX_RECORD_CHARS)
    if not clean_document.strip():
        return {"status": "error", "stored": False, "reason": "Document is empty.", "fake_success": False}
    collection = _training_collection()
    if collection is None:
        return {"status": "error", "stored": False, "reason": "Training collection unavailable.", "fake_success": False}

    content_hash = hashlib.sha256(clean_document.encode("utf-8", errors="ignore")).hexdigest()
    item_id = f"knowledge_{uuid.uuid5(uuid.NAMESPACE_URL, content_hash)}"
    metadata = dict(metadata)
    metadata["content_hash"] = content_hash
    metadata["document_chars"] = len(clean_document)
    metadata = _json_metadata(metadata)
    try:
        collection.upsert(
            ids=[item_id],
            documents=[clean_document],
            metadatas=[metadata],
            embeddings=[_embedding_11d(clean_document, metadata)],
        )
        return {
            "status": "success",
            "stored": True,
            "item_id": item_id,
            "storage_target": f"chroma:{os.getenv('WINTRIP_TRAINING_COLLECTION', 'wintrip_training_11d')}",
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "error", "stored": False, "reason": str(exc), "fake_success": False}


def _topic_from_heading(section: dict[str, Any], index: int) -> dict[str, Any]:
    title = str(section.get("title") or "")
    return {
        "id": str(section.get("id") or _slug(title)),
        "index": index,
        "title": title,
        "query": _topic_query(str(section.get("path") or ""), title),
        "section": title,
        "section_path": str(section.get("path") or title),
        "source_path": str(knowledge_list_path()),
        "line": int(section.get("line") or 0),
        "kind": "heading",
        "curriculum": classify_record(title, {"source": str(knowledge_list_path())}),
    }


def _topic_query(section_path: str, text: str) -> str:
    base = f"Ouroboros lokaal AI {section_path} {text}".strip()
    return re.sub(r"\s+", " ", base)[:500]


def _dedupe_topics(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for topic in topics:
        key = str(topic.get("id") or _slug(str(topic.get("title") or "")))
        if key in seen:
            continue
        seen.add(key)
        topic = dict(topic)
        topic["index"] = len(result)
        result.append(topic)
    return result


def _select_topics(
    topics: list[dict[str, Any]],
    completed: set[str],
    limit: int,
    start_index: int | None,
    records: list[dict[str, Any]] | None = None,
    source_type: str = "",
) -> list[dict[str, Any]]:
    candidates = topics
    if start_index is not None:
        candidates = [topic for topic in topics if int(topic.get("index") or 0) >= int(start_index)]
        return [topic for topic in candidates if str(topic.get("id")) not in completed][:limit]

    pending = [topic for topic in candidates if str(topic.get("id")) not in completed]
    if not pending:
        return []

    coverage = _curriculum_counts([record for record in (records or []) if record.get("status") == "success"])
    attempts = _topic_attempt_counts(records or [], source_type)

    def sort_key(topic: dict[str, Any]) -> tuple[int, int, int]:
        topic_id = str(topic.get("id") or "")
        return (
            coverage.get(_topic_curriculum_primary(topic), 0),
            attempts.get(topic_id, 0),
            int(topic.get("index") or 0),
        )

    return sorted(pending, key=sort_key)[:limit]


def _topic_selection_summary(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": topic.get("id"),
            "index": topic.get("index"),
            "title": topic.get("title"),
            "curriculum_primary": _topic_curriculum_primary(topic),
        }
        for topic in topics
    ]


def _topic_curriculum_primary(topic: dict[str, Any]) -> str:
    title = str(topic.get("title") or "")
    section = str(topic.get("section_path") or topic.get("section") or "")
    direct = str(classify_record(f"{section} {title}", {}).get("primary") or "").strip()
    if direct and direct != "general":
        return direct

    curriculum = topic.get("curriculum") if isinstance(topic.get("curriculum"), dict) else {}
    primary = str(curriculum.get("primary") or "").strip()
    if primary:
        return primary
    return direct or "general"


def _topic_attempt_counts(records: list[dict[str, Any]], source_type: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if source_type and record.get("source_type") != source_type:
            continue
        topic_id = str(record.get("topic_id") or "")
        if not topic_id:
            continue
        counts[topic_id] = counts.get(topic_id, 0) + 1
    return counts


def _completed_topics(records: list[dict[str, Any]], source_type: str) -> set[str]:
    return {
        str(record.get("topic_id"))
        for record in records
        if record.get("source_type") == source_type and record.get("status") == "success"
    }


def _next_topics(topics: list[dict[str, Any]], completed: set[str], limit: int) -> list[dict[str, Any]]:
    return [
        {"id": topic.get("id"), "index": topic.get("index"), "title": topic.get("title"), "section": topic.get("section")}
        for topic in topics
        if str(topic.get("id")) not in completed
    ][:limit]


def _record_metadata(
    topic: dict[str, Any],
    source_type: str,
    result: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    document_hint = f"{topic.get('section_path')} {topic.get('title')} {result.get('document') or result.get('scrubbed_text') or ''}"
    curriculum = classify_record(
        document_hint,
        {
            "source_type": source_type,
            "topic": topic.get("title"),
            "section": topic.get("section_path"),
        },
    )
    source = result.get("source") or result.get("source_url") or result.get("url") or result.get("target_url") or str(topic.get("source_path") or "")
    return {
        "type": "knowledge_acquisition_record",
        "source": str(source),
        "source_type": source_type,
        "approval_status": "approved",
        "trust_level": _trust_level_for_source(source_type),
        "taint": _taint_for_source(source_type, result),
        "topic_id": str(topic.get("id") or ""),
        "topic_title": str(topic.get("title") or "")[:500],
        "topic_index": int(topic.get("index") or 0),
        "section": str(topic.get("section") or "")[:500],
        "section_path": str(topic.get("section_path") or "")[:1000],
        "knowledge_list_path": str(topic.get("source_path") or knowledge_list_path()),
        "model": model if source_type == "gemma_distillation" else "",
        "browser_action_performed": bool(result.get("browser_action_performed", False)),
        "bulk_scraping": bool(result.get("bulk_scraping", False)),
        "curriculum_primary": curriculum.get("primary", "general"),
        "curriculum_labels": ",".join(curriculum.get("labels") or []),
        "ingested_at": _now_iso(),
        "dimension_count": 11,
        "dream_hz": 418.0,
        "resonance_score": 0.7,
        "fake_success": False,
    }


def _trust_level_for_source(source_type: str) -> str:
    if source_type == "gemma_distillation":
        return "local_model_distilled"
    if source_type == "brave_llm_context":
        return "external_web_brave_llm_context"
    return "external_web_scrubbed"


def _taint_for_source(source_type: str, result: dict[str, Any]) -> str:
    if source_type == "gemma_distillation":
        return "local_distillation"
    if source_type == "brave_llm_context":
        return str(result.get("taint") or "untrusted_web:brave_llm_context")
    return str(result.get("taint") or "scrubbed_browser")


def _training_collection() -> Any:
    try:
        from controller.chroma_runtime import get_or_create_collection

        collection_name = os.getenv("WINTRIP_TRAINING_COLLECTION", "wintrip_training_11d")
        return get_or_create_collection(name=collection_name)
    except Exception:
        return None


def _embedding_11d(document: str, metadata: dict[str, Any]) -> list[float]:
    seed = "|".join(
        [
            document[:4000],
            str(metadata.get("source_type", "")),
            str(metadata.get("curriculum_primary", "")),
            str(metadata.get("topic_id", "")),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).digest()
    values = []
    for index in range(11):
        raw = int.from_bytes(digest[index * 2 : index * 2 + 2], "big")
        values.append(round((raw / 65535.0) * 2.0 - 1.0, 6))
    return values


def _json_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[str(key)] = value
        else:
            clean[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True)[:1000]
    return clean


def _curriculum_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get("curriculum_primary") or "general")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _load_state() -> dict[str, Any]:
    path = knowledge_state_path()
    if not path.exists():
        return {"records": [], "fake_success": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"records": [], "fake_success": False}
    except Exception as exc:
        return {"records": [], "last_error": f"Cannot read knowledge state: {exc}", "fake_success": False}


def _save_state(state: dict[str, Any]) -> None:
    path = knowledge_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _limit_text(text: Any, limit: int) -> str:
    clean = str(text or "").replace("\x00", "")
    clean = re.sub(r"[ \t]+", " ", clean)
    return clean[:limit]


def _clean_inline(text: str) -> str:
    clean = re.sub(r"`([^`]+)`", r"\1", text)
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
    clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
    clean = clean.replace("–", "-")
    return re.sub(r"\s+", " ", clean).strip()


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug[:120] or hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
