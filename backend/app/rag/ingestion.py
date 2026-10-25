"""Document ingestion for RAG evaluation.

Supports PDF, TXT and Markdown. Uploads are validated on extension, declared
content type and byte size before anything is parsed; parsing never executes
uploaded content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import ValidationFailedError
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/octet-stream",  # browsers often send this for .md
}

_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_WHITESPACE = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")


@dataclass(slots=True)
class ParsedDocument:
    filename: str
    text: str
    page_count: int = 1
    pages: list[str] | None = None


def validate_upload(filename: str, content_type: str | None, size: int) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationFailedError(
            f"Unsupported file type '{suffix or filename}'. Allowed: PDF, TXT, Markdown.",
            details={"allowed": sorted(ALLOWED_EXTENSIONS)},
        )
    if content_type and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise ValidationFailedError(
            f"Unexpected content type '{content_type}' for a {suffix} file.",
        )
    if size <= 0:
        raise ValidationFailedError("Uploaded file is empty.")
    if size > settings.max_upload_bytes:
        raise ValidationFailedError(
            f"File is {size / 1e6:.1f} MB; the limit is "
            f"{settings.max_upload_bytes / 1e6:.0f} MB."
        )
    return suffix


def safe_filename(filename: str) -> str:
    """Strip any path component and unusual characters from an uploaded name."""
    base = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]+", "_", base).strip() or "document"
    return cleaned[:180]


def _clean_markdown(text: str) -> str:
    text = _FRONT_MATTER.sub("", text)
    text = _CODE_FENCE.sub(" ", text)
    text = _MD_IMAGE.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`>]{1,3}", "", text)
    return text


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    return _BLANKS.sub("\n\n", text).strip()


def parse_document(path: Path, *, filename: str | None = None) -> ParsedDocument:
    """Parse a stored file into plain text (plus per-page text for PDFs)."""
    name = filename or path.name
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise ValidationFailedError(
                "PDF support requires the `pypdf` package to be installed."
            ) from exc
        try:
            reader = PdfReader(str(path))
            pages = [(page.extract_text() or "") for page in reader.pages]
        except Exception as exc:
            raise ValidationFailedError(f"Could not read PDF '{name}': {exc}") from exc
        pages = [_clean(p) for p in pages]
        text = "\n\n".join(p for p in pages if p)
        if not text.strip():
            raise ValidationFailedError(
                f"No extractable text found in '{name}'. Scanned PDFs need OCR first."
            )
        return ParsedDocument(filename=name, text=text, page_count=len(pages), pages=pages)

    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".md", ".markdown"}:
        raw = _clean_markdown(raw)
    text = _clean(raw)
    if not text:
        raise ValidationFailedError(f"'{name}' contained no readable text.")
    return ParsedDocument(filename=name, text=text, page_count=1, pages=[text])
