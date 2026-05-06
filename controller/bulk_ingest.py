#!/usr/bin/env python3
"""
Wintrip bulk_ingest.py

Doel:
- Vul ChromaDB met lokale documenten in kleine batches.
- Ondersteunt PDF, TXT, MD, JSON, CSV, DOCX.
- Gebruikt Ollama embeddings via nomic-embed-text:latest.
- Schrijft uitsluitend naar de lokale ChromaDB.
- Geschikt voor persona-gebonden kennis.
- Voorbereid op latere uitbreiding met incremental ingest, deduplicatie en stricte sandbox policies.

Voorbeeld:
python bulk_ingest.py \
  --input-dir /Users/philip/WintripKnowledge \
  --persona general \
  --collection wintrip_knowledge \
  --db-path ./wintrip_brain \
  --ollama-url http://localhost:11434/api/embeddings \
  --embed-model nomic-embed-text:latest
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence

from dotenv import load_dotenv

import docx
import PyPDF2
from chromadb.api.models.Collection import Collection
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from controller.chroma_runtime import chroma_client, get_or_create_collection


# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("wintrip.bulk_ingest")


# =========================
# Config models
# =========================
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".json", ".csv", ".docx"}
CODE_EXTENSIONS = {".java", ".py", ".php", ".swift", ".cpp", ".cxx", ".cc", ".hpp", ".h"}


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    text: str
    metadata: dict


# =========================
# Helpers
# =========================
def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def iter_files(input_dir: Path, recursive: bool = True) -> Iterator[Path]:
    walker = input_dir.rglob("*") if recursive else input_dir.glob("*")
    for path in walker:
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in SUPPORTED_EXTENSIONS or ext in CODE_EXTENSIONS:
            yield path


# =========================
# Readers
# =========================
def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_pdf(path: Path) -> str:
    pages: List[str] = []
    with path.open("rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            if page_text.strip():
                pages.append(page_text)
    return "\n\n".join(pages)


def read_docx(path: Path) -> str:
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_csv(path: Path) -> str:
    rows: List[str] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(rows)


def read_json(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = json.loads(raw)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return raw


def extract_text_from_file(path: Path) -> str:
    ext = path.suffix.lower()

    if ext == ".pdf":
        return normalize_whitespace(read_pdf(path))
    if ext == ".docx":
        return normalize_whitespace(read_docx(path))
    if ext == ".csv":
        return normalize_whitespace(read_csv(path))
    if ext == ".json":
        return normalize_whitespace(read_json(path))
    return normalize_whitespace(read_text_file(path))


# =========================
# Chunking strategy
# =========================
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
    """
    Semantisch chunking-light zonder externe NLP dependencies.

    Strategie:
    1. Eerst per paragraaf.
    2. Als een paragraaf te groot is: splits op zinnen.
    3. Voeg kleine delen samen tot bruikbare blokken.
    4. Voeg overlap toe om contextverlies te beperken.
    """
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
# Metadata strategy
# =========================
def infer_language_from_extension(path: Path) -> str | None:
    mapping = {
        ".java": "java",
        ".py": "python",
        ".php": "php",
        ".swift": "swift",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".cc": "cpp",
        ".hpp": "cpp",
        ".h": "cpp",
    }
    return mapping.get(path.suffix.lower())


def infer_doc_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext == ".pdf":
        return "pdf"
    if ext in {".md", ".markdown"}:
        return "markdown"
    if ext == ".docx":
        return "docx"
    if ext == ".json":
        return "json"
    if ext == ".csv":
        return "csv"
    return "text"


# =========================
# Chroma wrapper
# =========================
class WintripIngestor:
    def __init__(
        self,
        db_path: Path,
        collection_name: str,
        ollama_url: str,
        embed_model: str,
        batch_size: int,
        reset_collection: bool = False,
    ) -> None:
        self.client = chroma_client(persist_dir=db_path)
        self.embedding_fn = OllamaEmbeddingFunction(
            url=ollama_url,
            model_name=embed_model,
        )

        if reset_collection:
            try:
                self.client.delete_collection(collection_name)
                logger.warning("Bestaande collectie verwijderd: %s", collection_name)
            except Exception:
                pass

        self.collection: Collection = get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            persist_dir=db_path,
            metadata={"owner": "wintrip", "embedding_model": embed_model},
        )
        self.batch_size = batch_size

    def document_already_ingested(self, file_sha256: str) -> bool:
        result = self.collection.get(where={"file_sha256": file_sha256}, limit=1)
        ids = result.get("ids", []) if result else []
        return len(ids) > 0

    def add_chunks(self, chunks: Sequence[ChunkRecord]) -> None:
        if not chunks:
            return

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            ids = [c.chunk_id for c in batch]
            docs = [c.text for c in batch]
            metas = [c.metadata for c in batch]
            self.collection.add(ids=ids, documents=docs, metadatas=metas)
            logger.info("Batch toegevoegd: %s chunks", len(batch))


# =========================
# Build chunk records
# =========================
def build_chunk_records(
    path: Path,
    text: str,
    persona: str,
    source_group: str,
    chunk_max_chars: int,
    chunk_min_chars: int,
    chunk_overlap_chars: int,
) -> List[ChunkRecord]:
    file_sha = sha256_file(path)
    doc_type = infer_doc_type(path)
    language = infer_language_from_extension(path)
    chunks = chunk_text_semantic(
        text,
        max_chars=chunk_max_chars,
        min_chars=chunk_min_chars,
        overlap_chars=chunk_overlap_chars,
    )

    records: List[ChunkRecord] = []
    total = len(chunks)

    for index, chunk in enumerate(chunks):
        chunk_sha = sha256_text(chunk)
        chunk_id = f"{path.stem}-{index}-{uuid.uuid5(uuid.NAMESPACE_URL, chunk_sha)}"
        metadata = {
            "type": doc_type,
            "source": str(path),
            "source_type": path.suffix.lower().strip('.') or "unknown",
            "persona": persona,
            "importance": 1.0,
            "interaction_id": "bulk",
            "source_group": source_group,
            "source_path": str(path),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "doc_type": doc_type,
            "language": language or "unknown",
            "chunk_index": index,
            "chunk_count": total,
            "content_hash": chunk_sha,
            "source_hash": file_sha,
            "file_sha256": file_sha,
            "chunk_sha256": chunk_sha,
            "char_count": len(chunk),
            "sandbox_only": True,
            "trust_level": "local_first",
            "ingested_at": datetime.utcnow().isoformat(),
            "title": path.name,
            "tags": f"bulk_ingest,{source_group}"
        }
        records.append(ChunkRecord(chunk_id=chunk_id, text=chunk, metadata=metadata))

    return records


# =========================
# Main ingest flow
# =========================
def ingest_directory(
    ingestor: WintripIngestor,
    input_dir: Path,
    persona: str,
    source_group: str,
    recursive: bool,
    chunk_max_chars: int,
    chunk_min_chars: int,
    chunk_overlap_chars: int,
    skip_duplicates: bool,
) -> None:
    files = list(iter_files(input_dir=input_dir, recursive=recursive))
    logger.info("%s ondersteunde bestanden gevonden in %s", len(files), input_dir)

    processed_files = 0
    skipped_files = 0
    total_chunks = 0

    for path in files:
        try:
            file_sha = sha256_file(path)
            if skip_duplicates and ingestor.document_already_ingested(file_sha):
                skipped_files += 1
                logger.info("Overgeslagen (al geïngest): %s", path.name)
                continue

            text = extract_text_from_file(path)
            if not text.strip():
                skipped_files += 1
                logger.warning("Leeg of onleesbaar bestand overgeslagen: %s", path)
                continue

            records = build_chunk_records(
                path=path,
                text=text,
                persona=persona,
                source_group=source_group,
                chunk_max_chars=chunk_max_chars,
                chunk_min_chars=chunk_min_chars,
                chunk_overlap_chars=chunk_overlap_chars,
            )
            if not records:
                skipped_files += 1
                logger.warning("Geen bruikbare chunks gevormd voor: %s", path)
                continue

            ingestor.add_chunks(records)
            processed_files += 1
            total_chunks += len(records)
            logger.info("Geïngest: %s | %s chunks", path.name, len(records))

        except Exception as exc:
            skipped_files += 1
            logger.exception("Fout tijdens ingest van %s: %s", path, exc)

    logger.info(
        "Klaar | verwerkt=%s | overgeslagen=%s | chunks=%s | collectie_count=%s",
        processed_files,
        skipped_files,
        total_chunks,
        ingestor.collection.count(),
    )


# =========================
# CLI
# =========================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bulk ingest lokale kennis in ChromaDB voor Wintrip")
    parser.add_argument("--input-dir", required=True, help="Map met documenten")
    parser.add_argument("--persona", default="general", help="Persona label voor metadata")
    parser.add_argument("--source-group", default="manual_ingest", help="Bronlabel voor metadata")
    parser.add_argument("--collection", default="wintrip_knowledge", help="Naam van de Chroma collectie")
    from knowledge_base import CHROMA_PERSIST_DIR
    parser.add_argument("--db-path", default=CHROMA_PERSIST_DIR, help="Pad naar lokale ChromaDB")
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/embeddings", help="Ollama embeddings endpoint")
    parser.add_argument("--embed-model", default="nomic-embed-text:latest", help="Ollama embedding model")
    parser.add_argument("--batch-size", type=int, default=32, help="Aantal chunks per Chroma add")
    parser.add_argument("--chunk-max-chars", type=int, default=1200, help="Max chars per chunk")
    parser.add_argument("--chunk-min-chars", type=int, default=350, help="Min chars per chunk")
    parser.add_argument("--chunk-overlap-chars", type=int, default=180, help="Overlap in chars")
    parser.add_argument("--no-recursive", action="store_true", help="Niet recursief door submappen lopen")
    parser.add_argument("--reset-collection", action="store_true", help="Verwijder bestaande collectie eerst")
    parser.add_argument("--allow-duplicate-files", action="store_true", help="Niet dedupliceren op file hash")
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        logger.error("Input map bestaat niet of is geen map: %s", input_dir)
        return 1

    db_path.mkdir(parents=True, exist_ok=True)

    ingestor = WintripIngestor(
        db_path=db_path,
        collection_name=args.collection,
        ollama_url=args.ollama_url,
        embed_model=args.embed_model,
        batch_size=args.batch_size,
        reset_collection=args.reset_collection,
    )

    ingest_directory(
        ingestor=ingestor,
        input_dir=input_dir,
        persona=args.persona,
        source_group=args.source_group,
        recursive=not args.no_recursive,
        chunk_max_chars=args.chunk_max_chars,
        chunk_min_chars=args.chunk_min_chars,
        chunk_overlap_chars=args.chunk_overlap_chars,
        skip_duplicates=not args.allow_duplicate_files,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
