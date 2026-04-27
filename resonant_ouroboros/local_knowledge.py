"""Bounded local-directory knowledge ingestion for Awake Keeper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from .self_model import compact_text


DEFAULT_TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}


@dataclass(frozen=True)
class LocalKnowledgeDocument:
    root: Path
    path: Path
    text: str

    @property
    def relative_path(self) -> str:
        try:
            return str(self.path.relative_to(self.root))
        except ValueError:
            return str(self.path)

    @property
    def title(self) -> str:
        return self.relative_path

    @property
    def source_label(self) -> str:
        return str(self.path)

    @property
    def document_text(self) -> str:
        return (
            f"Local knowledge file: {self.relative_path}\n"
            f"Root: {self.root}\n\n"
            f"{self.text}"
        )

    @property
    def summary(self) -> str:
        return compact_text(self.text, 700)


class LocalKnowledgeIngestor:
    """Read a small, safe subset of local project files into 11D memory."""

    def __init__(
        self,
        roots: list[str | Path],
        *,
        max_files: int = 80,
        max_bytes_per_file: int = 80_000,
        extensions: set[str] | None = None,
    ):
        self.roots = [Path(root) for root in roots if str(root).strip()]
        self.max_files = max(0, int(max_files))
        self.max_bytes_per_file = max(1_000, int(max_bytes_per_file))
        self.extensions = extensions or DEFAULT_TEXT_EXTENSIONS

    @classmethod
    def from_env(cls) -> "LocalKnowledgeIngestor":
        raw = os.getenv("AWAKE_KEEPER_EXTRA_KNOWLEDGE_PATHS", "")
        separators = [os.pathsep, ","]
        values = [raw]
        for separator in separators:
            if separator in raw:
                values = [item for chunk in values for item in chunk.split(separator)]
        return cls(
            values,
            max_files=int(os.getenv("AWAKE_KEEPER_EXTRA_KNOWLEDGE_MAX_FILES", "80")),
            max_bytes_per_file=int(os.getenv("AWAKE_KEEPER_EXTRA_KNOWLEDGE_MAX_BYTES", "80000")),
        )

    def load_documents(self) -> list[LocalKnowledgeDocument]:
        documents: list[LocalKnowledgeDocument] = []
        for root in self.roots:
            if len(documents) >= self.max_files:
                break
            root = root.expanduser()
            if not root.exists():
                continue
            if root.is_file():
                doc = self._read_document(root.parent, root)
                if doc:
                    documents.append(doc)
                continue
            for path in sorted(root.rglob("*")):
                if len(documents) >= self.max_files:
                    break
                if not path.is_file() or self._is_skipped(path):
                    continue
                doc = self._read_document(root, path)
                if doc:
                    documents.append(doc)
        return documents

    def _is_skipped(self, path: Path) -> bool:
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            return True
        if path.suffix.lower() not in self.extensions:
            return True
        return False

    def _read_document(self, root: Path, path: Path) -> LocalKnowledgeDocument | None:
        if self._is_skipped(path):
            return None
        try:
            raw = path.read_bytes()[: self.max_bytes_per_file]
        except OSError:
            return None
        if b"\x00" in raw:
            return None
        text = raw.decode("utf-8", errors="ignore")
        text = "\n".join(line.rstrip() for line in text.splitlines())
        if not text.strip():
            return None
        return LocalKnowledgeDocument(root=root, path=path, text=compact_text(text, self.max_bytes_per_file))
