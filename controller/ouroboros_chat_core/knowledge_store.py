from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def read_text(path: Path, limit: int = 80_000) -> str:
    ext = path.suffix.lower().lstrip(".")
    try:
        if ext in {"txt", "md", "csv", "json", "yaml", "yml", "toml", "py", "ts", "tsx", "js", "jsx", "rs", "go", "java", "c", "cc", "cpp", "h", "hpp", "css", "html", "sql", "sh"}:
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
        if ext == "pdf":
            import PyPDF2

            pages = []
            with path.open("rb") as handle:
                reader = PyPDF2.PdfReader(handle)
                for page in reader.pages[:16]:
                    pages.append(page.extract_text() or "")
            return "\n".join(pages)[:limit]
        if ext == "docx":
            import docx

            return "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)[:limit]
    except Exception as exc:
        return f"[knowledge read error: {exc}]"
    return ""


class KnowledgeStore:
    def snippets_for_persona(self, persona: dict[str, Any], query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        files = persona.get("knowledge_files") or []
        sources = persona.get("knowledge_sources") or []
        terms = [term.lower() for term in re.findall(r"\w{3,}", query or "")[:12]]
        snippets: list[dict[str, Any]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            path_value = str(item.get("path") or "").strip()
            if not path_value:
                continue
            path = Path(path_value).expanduser()
            if not path.exists() or not path.is_file():
                continue
            text = read_text(path)
            if not text.strip():
                continue
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms) if terms else 1
            if score <= 0:
                continue
            start = 0
            for term in terms:
                found = lowered.find(term)
                if found >= 0:
                    start = max(0, found - 280)
                    break
            snippet = text[start : start + 1200].strip()
            snippets.append(
                {
                    "source": str(path),
                    "label": item.get("label") or item.get("filename") or path.name,
                    "snippet": snippet,
                    "score": score,
                }
            )
        for item in sources:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("href") or "").strip()
            label = str(item.get("label") or item.get("title") or url).strip()
            note = str(item.get("note") or item.get("description") or "").strip()
            if not url:
                continue
            haystack = f"{label} {url} {note}".lower()
            score = sum(haystack.count(term) for term in terms) if terms else 1
            if score <= 0 and terms:
                continue
            snippets.append(
                {
                    "source": url,
                    "label": label or url,
                    "snippet": "\n".join(part for part in [f"Knowledge link: {url}", note] if part).strip(),
                    "score": max(score, 1),
                    "kind": "link",
                }
            )
        snippets.sort(key=lambda item: item["score"], reverse=True)
        return snippets[:limit]
