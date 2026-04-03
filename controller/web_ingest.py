#!/usr/bin/env python3
"""
Wintrip web_ingest.py (v1)

Doel:
- Haal tekst op van een URL via HTTP.
- Clean HTML (verwijder boilerplate).
- Gebruik EXACT dezelfde chunking-logica als bulk_ingest.py.
- Sla op in de lokale ChromaDB (Wintrip Brain).
- Deterministische IDs voor deduplicatie.
"""

import argparse
import hashlib
import logging
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse
from typing import List

import requests
from bs4 import BeautifulSoup

# Voeg het root-pad toe aan sys.path voor imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from controller.knowledge_base import KnowledgeBase

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("wintrip.web_ingest")

# =========================
# Chunking Logica (EXACT gekopieerd uit bulk_ingest.py voor consistentie)
# =========================
def normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def split_paragraphs(text: str) -> List[str]:
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]

def split_sentences_fallback(text: str) -> List[str]:
    parts = re.split(r"(?<=[\.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]

def chunk_text_semantic(
    text: str,
    max_chars: int = 1200,
    min_chars: int = 350,
    overlap_chars: int = 180,
) -> List[str]:
    """Semantisch chunking-light. EXACTE kopie uit bulk_ingest.py."""
    text = normalize_whitespace(text)
    if not text:
        return []

    paragraphs = split_paragraphs(text)
    if not paragraphs:
        paragraphs = [text]

    units: List[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            units.append(para)
            continue
        sentences = split_sentences_fallback(para)
        if not sentences:
            for i in range(0, len(para), max_chars):
                units.append(para[i : i + max_chars])
            continue

        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    units.append(current)
                if len(sentence) <= max_chars:
                    current = sentence
                else:
                    for i in range(0, len(sentence), max_chars):
                        units.append(sentence[i : i + max_chars])
                    current = ""
        if current:
            units.append(current)

    merged: List[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip() if current else unit
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            merged.append(current)
        current = unit
    if current:
        merged.append(current)

    final_chunks: List[str] = []
    for i, chunk in enumerate(merged):
        chunk = chunk.strip()
        if not chunk:
            continue
        if len(chunk) < min_chars and final_chunks:
            prev = final_chunks.pop()
            joined = f"{prev}\n\n{chunk}"
            if len(joined) <= max_chars + min_chars:
                final_chunks.append(joined)
            else:
                final_chunks.append(prev)
                final_chunks.append(chunk)
        else:
            final_chunks.append(chunk)

    if overlap_chars <= 0 or len(final_chunks) <= 1:
        return final_chunks

    overlapped: List[str] = []
    for i, chunk in enumerate(final_chunks):
        if i == 0:
            overlapped.append(chunk)
            continue
        prev_tail = final_chunks[i - 1][-overlap_chars:]
        overlapped.append(f"{prev_tail}\n\n{chunk}".strip())

    return overlapped

# =========================
# Web Scraping Helpers
# =========================
def get_safe_filename_from_url(url: str) -> str:
    """Maakt een nette slug/bestandsnaam van de URL voor metadata."""
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path.strip("/")
    if not path:
        return domain
    
    # Pak laatste deel van het pad, of domein als pad leeg is
    slug = path.split("/")[-1] or domain
    # Alleen veilige karakters behouden
    slug = re.sub(r"[^a-zA-Z0-9\.\-]", "_", slug)
    return slug

def fetch_url_text(url: str, timeout: int = 15) -> str:
    """Haalt HTML op en extraheert de hoofdtekst."""
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        raise ValueError(f"Ongeldig URL schema: {parsed_url.scheme}")

    headers = {"User-Agent": "WintripBot/1.0 (Local AI Agent)"}
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    response = requests.get(url, headers=headers, timeout=timeout, verify=False)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside"]):
        tag.decompose()

    main_content = soup.find("main") or soup.find("article") or soup.find("body")
    if not main_content:
        return ""

    return normalize_whitespace(main_content.get_text(separator="\n"))

# =========================
# Ingest Logic
# =========================
def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()

def ingest_url(url: str, persona: str = "developer", source_group: str = "web_ingest") -> dict:
    """Verwerkt een URL en slaat chunks op in ChromaDB met deterministische IDs."""
    brain = KnowledgeBase()

    try:
        text = fetch_url_text(url)
        if not text:
            return {"url": url, "status": "failed", "error": "Geen tekst gevonden"}

        chunks = chunk_text_semantic(text)
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        safe_filename = get_safe_filename_from_url(url)
        
        doc_ids, documents, metadatas = [], [], []
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            chunk_sha = sha256_text(chunk)
            # Deterministische ID op basis van URL-hash, index en chunk-hash
            chunk_id = f"web-{url_hash}-{i}-{uuid.uuid5(uuid.NAMESPACE_URL, chunk_sha)}"
            
            metadata = {
                "persona": persona,
                "source_group": source_group,
                "source_type": "url",
                "source_url": url,
                "domain": domain,
                "filename": safe_filename,
                "extension": ".html",
                "doc_type": "webpage",
                "language": "unknown",
                "chunk_index": i,
                "chunk_count": total,
                "chunk_sha256": chunk_sha,
                "char_count": len(chunk),
                "sandbox_only": True,
                "trust_level": "external_web",
            }
            
            documents.append(chunk)
            metadatas.append(metadata)
            doc_ids.append(chunk_id)

        brain.collection.add(ids=doc_ids, documents=documents, metadatas=metadatas)
        logger.info("URL succesvol geïngest: %s (%s chunks)", url, total)
        return {"url": url, "status": "success", "chunks": total}

    except Exception as e:
        logger.exception("Fout bij ingest van %s", url)
        return {"url": url, "status": "failed", "error": str(e)}

def ingest_urls(urls: List[str], persona: str = "developer", source_group: str = "web_ingest") -> List[dict]:
    return [ingest_url(url, persona, source_group) for url in urls]

# =========================
# CLI
# =========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wintrip Web Ingest CLI")
    parser.add_argument("--url", help="URL om in te laden")
    args = parser.parse_args()
    if args.url:
        print(ingest_url(args.url))
    else:
        parser.print_help()
